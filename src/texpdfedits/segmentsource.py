import argparse
import logging
import re

# simple TeX parser
from TexSoup import TexSoup 
# more complex TeX parser and converter
from pylatexenc.latexwalker import LatexWalker, LatexEnvironmentNode, LatexMacroNode, LatexMathNode, LatexCharsNode, LatexGroupNode 
from pylatexenc.macrospec import LatexContextDb, MacroSpec, EnvironmentSpec

from itertools import count
from pathlib import Path

import sys
import subprocess

METADATA_FIELDS = ['title', 'author', 'address', 'email', 'thanks', 'subjclass', 'keywords', 'datereceived', 'daterevised', 'abstract']
UNIQUE_FIELDS = {'title', 'subjclass', 'datereceived', 'keywords', 'abstract'}
ALLOWED_MARK_ENVIRONMENTS = {'proof', 'enumerate', 'itemize', 'document', 'thebibliography', 'biblist', 'bibdiv', 'bibsec'}

DIFFPDF_DPI = 175
## so far it appears for some reason \eqrefs produce very small differences in
## the PDF output when the \markboxes are inserted
## (but from what I can tell nothing else causes differences)

## If there are 93 eqrefs on a page less than 50_000 pixels are marxed different
## (when using DPI = 175; the larger the DPI, the larger the number of pixel differences)
## And if a page breaks early by just one line the difference on that and subsequent pages is at
## least 275_000
## (based on from `diff-pdf teichmuller.pdf breakteich.pdf -v -s -m -g --output-diff=diff_break.pdf --dpi=175`),
## so I think marking a page as not different if it differs by less than 50_000 pixels at this DPI is quite conservative.
DIFFPDF_PER_PAGE_PIXEL_TOLERANCE = 50_000

SCALED_POINTS_PER_TEX_POINT = 2 ** 16 # 65536

## there are 72.27 tex pts in an inch, while there are 
## 72 bp (what tex calls a big point) in an inch, which is what
## pymupdf and other modern pdf systems use
TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO = 72 / 72.27

## allow for half a point discrepancy between x0 + width and x1
## in boxinfoToPDFRectangle()
WORD_BOX_WIDTH_TOLERANCE = 1

def sourceAsString(filename: str) -> str:
    with open(filename, 'r', encoding = 'utf-8') as f:
        tex_file_str = f.read()
    return tex_file_str

def getMetadata(soup) -> dict[str, list | str]:
    r"""Extracts metadata, issuing warnings if a unique field appears more than once
       soup.find_all() fails if multiple comments are used like
       `\author[J. Malone]%
       %
       {John Malone}` which shouldn't really appear anyway. Comments will typically be removed from the souce.
    """
    metadata = dict()
    for field in METADATA_FIELDS:
        metadata[field] = [str(s) for s in soup.find_all(field)]
        if field in UNIQUE_FIELDS:
            num_fields = len(metadata[field])
            if num_fields != 1:
                logging.warning(f'Found {num_fields} instances of {field} during getMetadata()')
            else:
                metadata[field] = str(metadata[field][0])
    return metadata

def getEnunciations(soup) -> set[str]:
    r"""gets the names of enunciations declared with \newtheorem"""
    newthms = soup.find_all('newtheorem')
    enunciation_names = set()
    for thm in newthms:
        if len(thm.args) < 1:
            logging.error(fr'Somehow a \newtheorem macro has less than one argument as parsed by TexSoup... exiting.')
            sys.exit(1)
        enunciation_names.add(str(thm.args[0].string))
    return enunciation_names

def runPdflatex(tex_str: str, tex_basename: str, output_dir: Path, runs: int = 2) -> subprocess.CompletedProcess:
    """Run pdflatex. Run twice by default to resolve cross-references"""
    with open(output_dir / tex_basename, 'w', encoding='utf-8') as f:
        f.write(tex_str)
    
    result = None
    for i in range(runs):
        logging.info(f"Running pdflatex (pass {i+1}/{runs})")
        result = subprocess.run(
            ['pdflatex', '-interaction=nonstopmode', tex_basename],
            cwd=output_dir,
            capture_output=True, # see result.stdout, result.stderr
            text=True,
            encoding='latin-1'
        )
        
        if result.returncode != 0:
            logging.error(f"pdflatex failed on pass {i+1} of {tex_basename}: {result.stderr}.")
            sys.exit(1)
        
    return result

def runDiffpdf(first_fname: str, second_fname: str, output_dir: Path) -> subprocess.CompletedProcess:
    first_stem = Path(first_fname).stem
    second_stem = Path(second_fname).stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    subprocess_command = ['diff-pdf',
                          f'--per-page-pixel-tolerance={DIFFPDF_PER_PAGE_PIXEL_TOLERANCE}',
                          f'--dpi={DIFFPDF_DPI}',
                          '--skip-identical',
                          '--grayscale',
                          '--mark-differences',
                          '--verbose',
                          f'--output-diff={diff_fname}',
                          first_fname,
                          second_fname]
    
    logging.info(f"Running `{' '.join(subprocess_command)}`...")
    result = subprocess.run(subprocess_command,
                            cwd=output_dir)
    
    if result.returncode != 0:
        logging.error(f"{first_fname} and {second_fname} are not identical. See {Path(output_dir) / diff_fname}")        
        sys.exit(1)
    else:
        logging.info(f"PDFs are identical according to diff-pdf")

    return result

def markNode(latex_node, allowed_environments: set[str]) -> str:
    counter = count(0)
    def markStr(string, is_inline_math = False):
        return rf'\markbox{{{"m" if is_inline_math else ""}{next(counter)}}}{{{string}}}'
        
    def recMark(node):
        if node.isNodeType(LatexEnvironmentNode):
            verbatim_contents = ''.join([n.latex_verbatim() for n in node.nodelist]) #every LatexEnvironmentNode has a nodelist
            reconstructed_whole = rf'\begin{{{node.envname}}}{verbatim_contents}\end{{{node.envname}}}'
            if node.latex_verbatim() != reconstructed_whole:
                # not sure if I should only check this if the environment is among allowed_environments                
                # but it's safer to check every environment encountered
                logging.error(f"pylatexenc environment node {node.latex_verbatim()} in markNode was malformed or parsed incorrectly")
                logging.debug(f"{verbatim_contents} != {reconstructed_whole}")                
                sys.exit(1)
            
            if node.envname in allowed_environments:
                marked_contents = ''
                for nested_node in node.nodelist:
                    marked_contents += recMark(nested_node)
                return rf'\begin{{{node.envname}}}{marked_contents}\end{{{node.envname}}}'
            else:
                return reconstructed_whole
            
        elif node.isNodeType(LatexMacroNode):
            return node.latex_verbatim()
        elif node.isNodeType(LatexMathNode):
            if node.displaytype == 'inline':
                return markStr(node.latex_verbatim(), is_inline_math = True)
            else:
                return node.latex_verbatim()
        elif node.isNodeType(LatexCharsNode):
            verb_str = node.latex_verbatim()
            ## mark every word in safe envs
            ## I'm tempted to not worry about inserting between punctuation, but that will probably go poorly?
            ## will definitely need to revamp how I'm finding text in the bibliography though. I might just segment it by bib or bibitem and then search each one
            ## invdividually for a string difference kind of thing.
            marked_str, num_subs = re.subn(r"(?<=[\t\n ])\b[a-zA-Z]+\b(?=[\t\n ])", lambda m: markStr(m.group(0)), verb_str)
            logging.debug(f"marked {num_subs} words in {verb_str}")
            return marked_str
        elif node.isNodeType(LatexGroupNode):
            # for the time being this means that naked group blocks are ignored---will need to revisit.
            # Ultimately will likely use a different, simpler parser
            return node.latex_verbatim()
        else:
            logging.warning(f"Encountered unrecognized latex node '{node.nodeType()}' during markNode().\n Writing node.latex_verbatim(): '{node.latex_verbatim()}'")
            return node.latex_verbatim()
        
    return recMark(latex_node), next(counter)

def get_preamble_and_document(nodelist):
    """Read in a list of pylatexenc.latexwalker.<Node>s and return the nodes which belong to the
       preamble and document"""
    num_document_envs = len(list(filter(lambda n: n.isNodeType(LatexEnvironmentNode) and n.envname == 'document', nodelist)))
    if num_document_envs != 1:
        logging.error(r"Found more (or less) than one `\begin{document}`s during getPreambleAndDocument(). Exiting unsuccessfully.")
        sys.exit(1)

    i = 0
    while nodelist[i].nodeType() != LatexEnvironmentNode:
        i += 1
    preamble_nodes = nodelist[:i]
    document_node = nodelist[i]
    
    if i+1 < len(nodelist):
        logging.debug(f"Discarded {len(nodelist)-(i+1)} latex nodes after `\\end{{document}}` during getPreambleAndDocument")

    return preamble_nodes, document_node

def texPointsToPDFpoints(tex_pts: float):
    return tex_pts * TEX_POINTS_TO_PDF_POINTS_CONVERSION_RATIO

def scaledPointsToPDFpoints(sp: int):
    tex_pts = sp / SCALED_POINTS_PER_TEX_POINT
    return texPointsToPDFpoints(tex_pts)

def unzipHbox(hbox):
    return hbox[0], tuple(map(lambda pts: texPointsToPDFpoints(float(pts)), hbox[1:]))

def unzipPos(stend_xy):
    return stend_xy[0], tuple(map(lambda spts: scaledPointsToPDFpoints(int(spts)), stend_xy[1:-1]))

def boxinfoToPDFRectangle(key, hbox, start_xy, end_xy):
    pgA, (width, height, depth) = unzipHbox(hbox)
    pgB, (x0, sy) = unzipPos(start_xy)
    pgC, (x1, ey) = unzipPos(end_xy)

    if pgB != pgC:
        logging.debug(f"box '{key}' spanned multiple pages ({pgA} {pgB} {pgC}; ignoring")
        return None
    if sy != ey:
        logging.debug(f"box '{key}' start and end y positions were not equal: '{sy} != {ey}'; ignoring")
        return None
    if abs(x0 + width - x1) > WORD_BOX_WIDTH_TOLERANCE:
        logging.debug(f"box '{key}' abs(x0 + width - x1) = abs({x0 + width} - {x1}) = {abs(x0 + width - x1)} > {WORD_BOX_WIDTH_TOLERANCE}; ignoring")
        return None

    ## lower y values are closer to the top of the page
    ## return pageno, (x0, y0, x1, y1), where
    ## (x0, y0) is the top left corner and
    ## (x1, y1) is the bottom right corner of the rectangle
    return pgB, (x0, sy + height, x1, sy - depth)
        
def getWordBoxes(boxpositions_file_name: str, tot_num_boxes):
    word_boxes = dict()
    not_colon = r'([^:]*)'

    with open(boxpositions_file_name, 'r') as f:
        line = f.readline().strip()
        line_no = 1
        while line:
            box_info = re.match(fr"^(m?\d+):(pwhd|spxy|epxy):(\d+):{not_colon}:{not_colon}:{not_colon}$", line)
            if box_info == None:
                logging.error(f"Somehow line {line_no} of {boxpositions_file_name} '{repr(line)}' did not match the info spec. Exiting unsuccessfully.")
                sys.exit(1)
            matches = box_info.groups()
            key, label, values = matches[0], matches[1], tuple(map(lambda m: m.strip('pt'), matches[2:]))
            
            if key in word_boxes:
                if label in word_boxes[key]:
                    logging.error(f"""Somehow label '{label}' was already in '{word_boxes[key]}'.
                    There should be only three labels (and they should each appear at most once):
                    'pwhd' for page, width, height, depth; 'spxy' for start, page, x pos, y pos;
                    and 'epxy' for end, page, x pos, y pos""")
                    sys.exit(1)
                word_boxes[key][label] = values
            else:
                word_boxes[key] = {label:values}
            line = f.readline().strip()
            line_no += 1

    ## all marks should have exactly three fields, the hbox dimensions, start xy, and end xy positions
    if not all(filter(lambda x: x == 3, map(lambda d: len(d), list(word_boxes.values())))):
        logging.error(f"Information extracted from marks somehow differed from spec.")
        sys.exit(1)

    num_used_boxes = 0
    
    page_rectangles = dict()
    for key, info in word_boxes.items():
        res = boxinfoToPDFRectangle(key, info['pwhd'], info['spxy'], info['epxy'])
        if res == None:
            continue
        one_indexed_pageno, rectangle = res
        pageno = int(one_indexed_pageno) - 1
        if pageno in page_rectangles:
            page_rectangles[pageno][key] = rectangle
        else:
            page_rectangles[pageno] = {key:rectangle}
        num_used_boxes += 1

    logging.info(f"Used {num_used_boxes}/{tot_num_boxes} marked boxes.")
    return page_rectangles

def segment(tex_filename: str) -> str:
    r"""Return the TeX source that appears on outputted pages and as the arguments to certain dedicated commands or environments. Page-level partitioning is achieved with a hook to \shipout and frequent use of \mark. There's probably a better way, but this works..."""
    
    tex_str = sourceAsString(tex_filename)
    latex_context = LatexContextDb()
    # latex_context.add_context_category('macros',macros=[MacroSpec('mark', args_parser='{')])
    nodelist, _, _ = LatexWalker(tex_str, latex_context=latex_context).get_latex_nodes(pos=0)
    
    if ''.join([node.latex_verbatim() for node in nodelist]) != tex_str:
        logging.error(f"Verbatim string tex source was not preserved after LatexWalker parsing. The parser has likely failed. Exiting unsuccessfully.")
        sys.exit(1)

    logging.info("Getting soup...")
    soup = TexSoup(tex_str)
    logging.info("Finished getting soup.")

    logging.info("Extracting metadata...")
    enunciations = getEnunciations(soup)        
    metadata = getMetadata(soup) # dict[str, list]
    preambleNodes, documentNode = get_preamble_and_document(nodelist)

    preamble_str = ''.join([node.latex_verbatim() for node in preambleNodes])
    logging.info("Done.")

    mark_out_file = f'boxpositions_{Path(tex_filename).stem}.txt'
    tex_write_commands = fr"""
\newwrite\markfile
\immediate\openout\markfile={mark_out_file}
"""
    markbox_def = r"""
\newcommand{\markbox}[2]{%
  \setbox0=\hbox{#2}%
  \immediate\write\markfile{#1:pwhd:\the\value{page}:\the\wd0:\the\ht0:\the\dp0}%
  \pdfsavepos
  \write\markfile{#1:spxy:\the\value{page}:\the\pdflastxpos:\the\pdflastypos:}%
  #2% 
  \pdfsavepos
  \write\markfile{#1:epxy:\the\value{page}:\the\pdflastxpos:\the\pdflastypos:}%
}

"""
    logging.info("Inserting marks...")
    marked_document, num_marks = markNode(documentNode, ALLOWED_MARK_ENVIRONMENTS.union(enunciations))
    logging.info("Done.")
    
    marked_tex = preamble_str + tex_write_commands + markbox_def + marked_document

    tmp_dir = Path('tmp_segmentsource')
    Path.mkdir(tmp_dir, exist_ok = True)
    orig_filename = Path(tex_filename).name    
    marked_filename = Path(tex_filename).stem+'_marked.tex'

    def pdfFname(tex_fname):
        return Path(tex_fname).stem+'.pdf'

    process1 = runPdflatex(tex_str, orig_filename, tmp_dir)
    process2 = runPdflatex(marked_tex, marked_filename, tmp_dir)
    process3 = runDiffpdf(pdfFname(orig_filename), pdfFname(marked_filename), tmp_dir)

    
    ## temporary
    return marked_tex, tmp_dir / mark_out_file, num_marks

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python segmentsource.py',
                                     description = r'Segments source TeX by pages and metadata like \title, \author, \address, and abstract.')
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    
    filename = args.filename
    _level = logging.DEBUG if args.debug else logging.INFO
    
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    segment(filename)

    

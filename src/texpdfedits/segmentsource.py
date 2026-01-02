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
            # mark every word in safe envs
            marked_str, num_subs = re.subn(r"(?<= )\b[a-zA-Z]+\b(?= )", lambda m: markStr(m.group(0)), verb_str)
            logging.debug(f"marked {num_subs} words in {verb_str}")
            return marked_str
        elif node.isNodeType(LatexGroupNode):
            # for the time being this means that naked group blocks are ignored---will need to revisit.
            # Ultimately will likely use a different, simpler parser
            return node.latex_verbatim()
        else:
            logging.warning(f"Encountered unrecognized latex node '{node.nodeType()}' during markNode().\n Writing node.latex_verbatim(): '{node.latex_verbatim()}'")
            return node.latex_verbatim()
    return recMark(latex_node)

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
  \immediate\write\markfile{#1:whd{}:\the\value{page}:\the\wd0:\the\ht0:\the\dp0}%
  \pdfsavepos
  \write\markfile{#1:start:\the\value{page}:\the\pdflastxpos:\the\pdflastypos}%
  #2% 
  \pdfsavepos
  \write\markfile{#1:end{}:\the\value{page}:\the\pdflastxpos:\the\pdflastypos}%
}

"""
    logging.info("Inserting marks...")
    marked_document = markNode(documentNode, ALLOWED_MARK_ENVIRONMENTS.union(enunciations))
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
    
    return marked_tex
    

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

    

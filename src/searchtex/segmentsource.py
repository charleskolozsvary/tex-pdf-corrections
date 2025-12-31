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

METADATA_FIELDS = ['title', 'author', 'address', 'email', 'thanks',
                     'subjclass', 'keywords', 'datereceived', 'daterevised', 'abstract']
UNIQUE_FIELDS = {'title', 'subjclass', 'datereceived', 'keywords', 'abstract'}
ALLOWED_MARK_ENVIRONMENTS = {'proof', 'enumerate', 'itemize', 'document'}
PDF_DIFF_DPI = 500

def sourceAsString(filename: str) -> str:
    with open(filename, 'r', encoding = 'utf-8') as f:
        tex_file_str = f.read()
    return tex_file_str

def get_metadata(tex_str: str) -> dict[str, list | str]:
    r"""Extracts metadata, issuing warnings if a unique field appears more than once
       soup.find_all() fails if multiple comments are used like
       `\author[J. Malone]%
       %
       {John Malone}` which shouldn't really appear anyway.
    """
    soup = TexSoup(tex_str)
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

def getEnunciations(tex_str: str) -> set[str]:
    r"""gets the names of enunciations declared with \newtheorem"""
    soup = TexSoup(tex_str)
    newthms = soup.find_all('newtheorem')
    enunciation_names = set()
    for thm in newthms:
        if len(thm.args) < 1:
            logging.error(fr'Somehow a \newtheorem macro has less than one argument as parsed by TexSoup... exiting.')
            sys.exit(1)
        enunciation_names.add(str(thm.args[0].string))
    return enunciation_names

def runPdflatex(tex_str: str, tex_basename: str, output_dir: pathlib.Path, runs: int = 2) -> subprocess.CompletedProcess:
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
            text=True
        )
        
        if result.returncode != 0:
            logging.error(f"pdflatex failed on pass {i+1} of {tex_basename}: {result.stderr}.")
            sys.exit(1)
        
    return result

def runDiffpdf(first_fname: str, second_fname: str, output_dir: pathlib.Path) -> subprocess.CompletedProcess:
    first_stem = Path(first_fname).stem
    second_stem = Path(second_fname).stem
    diff_fname = f'diff_{first_stem}_{second_stem}.pdf'

    subprocess_command = ['diff-pdf',
                          f'--dpi={PDF_DIFF_DPI}',
                          '--skip-identical',
                          '--grayscale',
                          '--mark-differences',
                          '--verbose',
                          f'--output-diff={diff_fname}',
                          first_fname,
                          second_fname]
    
    logging.info(f"Running diff-pdf...")
    logging.debug(f"I.e., `{' '.join(subprocess_command)}`...")
    result = subprocess.run(subprocess_command,
                            cwd=output_dir,
                            capture_output=True,
                            text=True)
    
    if result.returncode != 0:
        logging.error(f"{first_fname} and {second_fname} are not identical:\n {result.stdout}\nSee {output_dir}")
        sys.exit(1)
    else:
        logging.info(f"PDFs are identical according to diff-pdf")

    return result

def markNode(latex_node, allowed_environments: set[str], markcsname) -> str:
    c = count(0)
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
            elif node.envname == 'abstract':
                return reconstructed_whole + rf'\marks\{markcsname}{{{next(c)}}}' # put the first mark directly after the abstract
            else:
                return reconstructed_whole
            
        elif node.isNodeType(LatexMacroNode) or node.isNodeType(LatexMathNode):
            return node.latex_verbatim()
        elif node.isNodeType(LatexCharsNode):
            verb_str = node.latex_verbatim()
            # mark every word in safe envs
            # negative lookahead (?!\.) to avoid 'end.' -> 'end\marks\pagemark{}.'
            marked_str, num_subs = re.subn(r'\b\w+\b(?!\.)', lambda m: rf'{m.group(0)}\marks\{markcsname}{{{next(c)}}}', verb_str)
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

    enunciations = getEnunciations(tex_str)        
    metadata = get_metadata(tex_str) # dict[str, list]
    preambleNodes, documentNode = get_preamble_and_document(nodelist)

    markcsname = 'segmentmark'
    preamble_str = ''.join([node.latex_verbatim() for node in preambleNodes])
    shipout_hook = fr"""
    \newmarks\{markcsname}
    \AddToHook{{shipout/after}}{{\message{{Shipping page \thepage: '\firstmarks\{markcsname}'--'\botmarks\{markcsname}'.}}}}
    """

    marked_document = markNode(documentNode, ALLOWED_MARK_ENVIRONMENTS.union(enunciations), markcsname)
    
    marked_str = preamble_str + shipout_hook + marked_document

    tmp_dir = Path('tmp_segmentsource')
    orig_filename = Path(tex_filename).name    
    marked_filename = Path(tex_filename).stem+'_marked.tex'

    def pdfFname(tex_fname):
        return Path(tex_fname).stem+'.pdf'

    process1 = runPdflatex(tex_str, orig_filename, tmp_dir)
    process2 = runPdflatex(marked_str, marked_filename, tmp_dir)
    process3 = runDiffpdf(pdfFname(orig_filename), pdfFname(marked_filename), tmp_dir)
    
    return marked_str
    

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

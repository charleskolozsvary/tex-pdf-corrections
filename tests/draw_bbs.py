import pymupdf
import argparse
from texpdfannots.extract import getStableAnnots, getCorrections, PDF_ANNOT_TEXT, PDF_ANNOT_CARET, PDF_ANNOT_STRIKE_OUT
from pathlib import Path

def drawAnnotBBs(filename, savefile = 'ann_bbs.pdf'):
    """draw bounding boxes of annotations in annotated PDF"""
    doc = pymupdf.open(filename)
    for page in doc:
        for annot in page.annots():
            if annot.type == PDF_ANNOT_TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save(savefile)
    return savefile


def drawStableAnnotBBs(filename, stable_annots, savefile = 'stable_ann_bbs.pdf'):
    """draw bounding boxes of stable annotations"""
    doc = pymupdf.open(filename)
    for pageno,page in enumerate(doc):
        for annot in annots[pageno]:
            if annot.type == PDF_ANNOT_TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save(savefile)
    return savefile


def drawLineBBs(filename, savefile = 'line_bbs.pdf'):
    """draw the bounding boxes of the lines from page.get_text('dict', sort=True)['blocks']"""
    doc = pymupdf.open(filename)
    for page in doc:
        blocks = page.get_text('dict', sort=True)['blocks']
        line_bbs = []
        line_bbs = [line['bbox'] for block in blocks for line in block['lines']]        
        for bb in line_bbs:
            box = page.add_freetext_annot(bb, '', text_color=(1,0,0))
            box.set_border(width=.5)
            box.update()
    doc.save(savefile)
    return savefile

def drawSelectionBBs(filename, savefile = 'sel_bbs.pdf'):
    """draw the bounding boxes of the selected text for each annotation"""
    file_stem = Path(filename).stem
    corrections = getCorrections(filename)
    for i, correction in enumerate(corrections):
        doc = pymupdf.open(filename)        
        page = doc[correction.pageno]
        bbs = correction.debug_bbs
        colors = [(1,0,0), (0,0,1)] if correction.type == PDF_ANNOT_CARET[1] else [(1,.25,.25), (.25,1,.25), (.25,.25,1)]
        for j, bb in enumerate(bbs):
            if bb.width == 0:
                continue
            box = page.add_freetext_annot(bb, '', text_color=colors[j])
            box.set_border(width=.75)
            box.update()
        single_save = Path('selections') / f'{file_stem}{i}_{savefile}'
        doc.save(single_save)
        print(single_save)            
        print(i, correction, end = '\n\n')        
    return savefile
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'extannots.py',
                                     description = 'Extract annotations and comments from an annotated PDF as a .json file')
    parser.add_argument('filename')
    args = parser.parse_args()
    filename = args.filename

    # doc = pymupdf.open(filename)
    # annots = getStableAnnots(doc, True)
    
    # drawAnnotBBs(filename)
    # line_bbs = drawLineBBs(filename)    
    # drawStableAnnotBBs(line_bbs, annots, 'combined_stable_line_bbs.pdf')

    drawSelectionBBs(filename)

    
    

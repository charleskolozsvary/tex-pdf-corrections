import pymupdf
import argparse
from texpdfannots.extract import getStableAnnots, getCorrections, PDF_ANNOT_TEXT, PDF_ANNOT_CARET, PDF_ANNOT_STRIKE_OUT
from pathlib import Path

import os

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
    out_str = ''
    corrections = getCorrections(filename)
    selection_file_names = []
    for i, correction in enumerate(corrections):
        doc = pymupdf.open(filename)
        page_count = doc.page_count
        if correction.pageno < page_count-1:
            doc.delete_pages(from_page=correction.pageno+1)
        if correction.pageno >= 1:
            doc.delete_pages(from_page=0, to_page=correction.pageno-1)
        assert doc.page_count == 1, "doc.page_count != 1"
        page = doc[0]
        bbs = correction.debug_bbs
        colors = [(1,0,0), (0,0,1)] if correction.type == PDF_ANNOT_CARET[1] else [(1,.25,.25), (.25,1,.25), (.25,.25,1)]
        for j, bb in enumerate(bbs):
            if bb.width == 0:
                continue
            box = page.add_freetext_annot(bb, '', text_color=colors[j])
            box.set_border(width=.75)
            box.update()
        print(f'{i}/{len(corrections)}')
        box = page.add_freetext_annot((5,5,550,350), str(correction), fontsize=10, fontname="Cour", text_color=(.7, .2, .5))
        box.update()
        single_save = Path('selections') / f'{Path(filename).stem}_selection_{i}.pdf'
        doc.save(single_save)
        out_str += f'{single_save}\n{i} {correction}\n\n'
        selection_file_names.append(single_save)
        
    combined_doc = pymupdf.open(filename)
    combined_doc.delete_pages(from_page=0, to_page=combined_doc.page_count-1)
    for single_page in selection_file_names:
        single_pdf = pymupdf.open(single_page)
        combined_doc.insert_pdf(single_pdf, annots=True)
    combined_doc.save(Path('selections') / f'{Path(filename).stem}_combined_selections.pdf')

    print("okay supposedly saved...")
    selection_dir = 'selections'
    os.system(f"rm {Path(selection_dir) / Path(filename).stem}_selection_*.pdf")
    
    with open(f'{Path(filename).stem}_corrections_out.txt', 'w') as f:
        f.write(out_str)
    
        
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

    
    

import pymupdf
import argparse
from texpdfedits.extract import getRobustAnnots, getCorrections, PDF_ANNOT_TEXT, PDF_ANNOT_CARET, PDF_ANNOT_STRIKE_OUT
from pathlib import Path

import os

def shipPdfFilename(filename, output_dir, unique_ending):
    out_dir = Path(output_dir)
    Path.mkdir(out_dir, exist_ok=True)
    return out_dir / f'{Path(filename).stem}_{unique_ending}.pdf'

def drawAnnots(filename, output_dir, unique_ending = 'orig_annots'):
    """draw bounding boxes of original annotations in annotated PDF"""
    doc = pymupdf.open(filename)
    for page in doc:
        for annot in page.annots():
            if annot.type == PDF_ANNOT_TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save(shipPdfFilename(filename, output_dir, unique_ending))
    return 0


def drawRobustAnnots(filename, robust_annots, output_dir, unique_ending = 'robust_annots'):
    """draw bounding boxes of robust annotations"""
    doc = pymupdf.open(filename)
    for pageno,page in enumerate(doc):
        for annot in annots[pageno]:
            if annot.type == PDF_ANNOT_TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save(shipPdfFilename(filename, output_dir, unique_ending))
    return 0


def drawLines(filename, output_dir, unique_ending = 'lines'):
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
    doc.save(shipPdfFilename(filename, output_dir, unique_ending))
    return 0

def drawEdits(filename, output_dir, unique_ending = 'edit_selections'):
    """draw the bounding boxes for extracting the selected text and the Edit json for each annotation
       yes this is more messy than it needs to be
    """
    corrections = getCorrections(filename)
    
    out_str = ''
    single_fname_prefix = Path(output_dir) / f'{Path(filename).stem}_{unique_ending}'
    singlepage_file_names = []
    print(f'Extracting annotations from {filename}...')
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
        box = page.add_freetext_annot((5,5,500,350), str(correction), fontsize=10, fontname="Cour", text_color=(.7, .2, .5))
        box.update()

        single_save = f'{single_fname_prefix}_{i}.pdf'
        doc.save(single_save)

        out_str += f'{single_save}\n{i} {correction}\n\n'
        
        singlepage_file_names.append(single_save)
        print(f'{i:3d}/{len(corrections):3d}')

    print(f'done. Files written to {output_dir}')
    combined_doc = pymupdf.open(filename)
    ## silly, but I'm not aware of a simpler way
    combined_doc.delete_pages(from_page=0, to_page=combined_doc.page_count-1)
    for single_page in singlepage_file_names:
        single_pdf = pymupdf.open(single_page)
        combined_doc.insert_pdf(single_pdf, annots=True)
        
    combined_doc.save(shipPdfFilename(filename, output_dir, unique_ending))

    print(f"Combined doc saved to {Path(output_dir)}...")
    print("Deleting intermediate PDFs...")
    
    os.system(f"rm {single_fname_prefix}_*.pdf")
    
    with open(f'{Path(output_dir) / Path(filename).stem}_corrections_out.txt', 'w') as f:
        f.write(out_str)

    return 0
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'python draw_bbs.py',
                                     description = 'Draw various bounding boxes')
    parser.add_argument('filename')
    args = parser.parse_args()
    filename = args.filename

    doc = pymupdf.open(filename)
    
    annots = getRobustAnnots(doc) # from extract.py
    bb_dir = Path('bbox_drawings')
    
    drawAnnots(filename, bb_dir)
    drawRobustAnnots(filename, annots, bb_dir)
    drawLines(filename, bb_dir)

    drawEdits(filename, bb_dir)

    
    

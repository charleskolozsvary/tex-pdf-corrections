from texpdfannots.extract import *

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
        
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'extannots.py',
                                     description = 'Extract annotations and comments from an annotated PDF as a .json file')
    parser.add_argument('filename')
    args = parser.parse_args()
    filename = args.filename

    doc = pymupdf.open(filename)
    annots = getStableAnnots(doc, True)
    
    drawAnnotBBs(filename)
    line_bbs = drawLineBBs(filename)    
    drawStableAnnotBBs(line_bbs, annots, 'combined_stable_line_bbs.pdf')

from texpdfedits.segmentsource import segment, getWordBoxes
import logging
import argparse
import pymupdf
from pathlib import Path

def drawWordBoxes(pdf_filename, page_word_rectangles, output_dir):
    save_file_name = Path(output_dir) / f'{Path(pdf_filename).stem}_word_boxes.pdf'
    logging.info(f"Drawing word boxes to {save_file_name}")
    doc = pymupdf.open(pdf_filename)
    for pg_no in page_word_rectangles:
        page = doc[pg_no]
        page_height = page.rect.height
        def toPymuY(y):
            nonlocal page_height
            return page_height - y
        for key, bb in page_word_rectangles[pg_no].items():
            x0, y0, x1, y1 = bb
            y0 = toPymuY(y0)
            y1 = toPymuY(y1)
            box = page.add_freetext_annot((x0, y0, x1, y1), key, text_color=(0,.25,.7), fontsize=3, fontname="Cour")
            box.set_border(width=.3)
            box.update()
            
    doc.save(save_file_name)
    logging.info("Done.")
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument("-d", "--debug", action="store_true", help='debugging output')
    
    args = parser.parse_args()
    _level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=_level, format='%(asctime)s - %(levelname)s - %(message)s')

    marked_tex, boxpositions_filename, num_boxes = segment(args.filename)

    page_word_rectangles = getWordBoxes(boxpositions_filename, num_boxes)
    output_dir = 'bbox_drawings'
    pdf_file_name = Path(args.filename).parent / f'{Path(args.filename).stem}.pdf' 
    
    drawWordBoxes(pdf_file_name, page_word_rectangles, output_dir)

    # logging.info(page_word_rectangles)

import pymupdf
import argparse
from copy import deepcopy

PDF_ANNOT_TEXT = (0, 'Text')
PDF_ANNOT_STRIKE_OUT = (11, 'StrikeOut')
PDF_ANNOT_CARET = (14, 'Caret')

class Annot:
    def __init__ (self, pageno, typename, info, xref, irt_xref, rect):
        self.type = typename
        self.info = info
        self.xref = xref
        self.irt_xref = irt_xref
        self.rect = rect
        self.pageno = pageno
    def __str__ (self):
        return str({'pageno':self.pageno,'type':self.type,'xref':self.xref,'irt_xref':self.irt_xref})
    def __repr__ (self):
        return str(self)

class CorrectionsAnnot:
    def __init__ (self, pageno, typename, message, text, rect):
        self.pageno = pageno
        self.type = typename
        self.message = message
        self.text = text
        self.rect = rect
    def __str__ (self):
        return str({'pageno':self.pageno,'type':self.type,'message':self.message,'text':self.text})
    def __repr__ (self):
        return str(self)

def get_stable_annots(doc, draw_boxes = False):
    """
    The bounding boxes of the original caret annotations often extend past the line they
    were inserted on, so they are resized to prevent that.

    pymupdf's annotations are also kind of fragile---they are strongly bound to the page they
    come from, and I've encountered issues with using the provided methods to update the
    annotations, so I'll just store the annotations with my own class which isn't tied to
    the page and stores the information correctly.
    """
    stable_annots = {pageno:[] for pageno in range(len(doc))}
    for pageno, page in enumerate(doc):
        blocks = page.get_text('dict', sort=True)['blocks']
        line_bbs = []
        line_bbs = [line['bbox'] for block in blocks for line in block['lines']]
        for annot in page.annots():
            if annot.type != (14, 'Caret'):
                stable_annots[pageno].append(Annot(pageno, annot.type, annot.info, annot.xref, annot.irt_xref, annot.rect))
                continue
            
            caretRect = annot.rect
            intersecting_line_bbs = list(filter(lambda l: caretRect.intersects(l), line_bbs))
            # bbbox = (x0, y0, x1, y1)
            highest_baseline_bb = sorted(intersecting_line_bbs, key = lambda bb : bb[3])[0]
            
            raisedRect = pymupdf.Rect(caretRect.top_left, caretRect.bottom_right)
            raisedRect.y1 = highest_baseline_bb[3]

            stable_annots[pageno].append(Annot(pageno,annot.type,annot.info,annot.xref,annot.irt_xref,raisedRect))

            if draw_boxes:                           
                orig = page.add_freetext_annot(annot.rect, "", text_color=(0,1,0))
                orig.set_border(width=.3)
                orig.update()                                       
            
                ah = page.add_freetext_annot(stable_annots[-1].rect, "", text_color=(0,0,1))
                ah.set_border(width=.3)
                ah.update() 

    if draw_boxes:
        doc.save('caret-isects.pdf')

    return stable_annots

def get_all_responses(stable_annots):
    """Return dictionary where dict[xref] => [annots for which annot.irt_xref == xref]"""
    all_responses = dict()
    for pageno, annots in stable_annots.items():
        for annot in annots: 
            if annot.irt_xref == 0:
                continue
            if annot.irt_xref in all_responses:
                all_responses[annot.irt_xref].append(annot)
            else:
                all_responses[annot.irt_xref] = [annot]
    return all_responses

def get_responses(annot, all_responses):
    """
    Return dictionary where dict[type] =>
    [annots for which annot.type == type and are a response to passed annot]
    """
    if annot.xref not in all_responses:
        return []

    resps_by_type = dict()
    for resp in all_responses[annot.xref]:
        if resp.type not in resps_by_type:
            resps_by_type[resp.type] = [resp]
        else:
            resps_by_type[resp.type].append(resp)

    for ann_type, resps in resps_by_type.items():
        resps_by_type[ann_type] = sorted(resps, key = lambda r: r.info['creationDate'])
    
    return resps_by_type

def get_corrections_annots(filename):
    """ return a list of annotations of the form
    {
      "pageno" : 1, #2, 3, etc.
      "type" : "StrikeOut" #(or Caret, Replace, Highlight, TextBox)
      "message": {
                   "head": "Original message", #(e.g., "COMP: roman")
                   "text_responses": ["text response to original message", "next response", ...]
                 }
      "text": "Next we prove that <selection>(1)</selection> is a consequence of" # surrounding and selected text
    # for standalone insertions, the caret tip will be marked <caret>
    }
    """
    doc = pymupdf.open(filename)
    stable_annots = get_stable_annots(doc)
    all_responses = get_all_responses(stable_annots)
    
    corrections = []
    for pageno, page in enumerate(doc):
        blocks = page.get_text('dict', sort=True)['blocks']
        for annot in stable_annots[pageno]: 
            if annot.irt_xref != 0:
                # only true for text responses and annotations which combine
                # with another to make an annotation of type 'Replace'
                continue
            responses = get_responses(annot, all_responses)
            text_responses = responses[PDF_ANNOT_TEXT] if PDF_ANNOT_TEXT in responses else []

            def is_replace_annot(ann, ann_resps):
                if not (ann.type == PDF_ANNOT_STRIKE_OUT or ann.type == PDF_ANNOT_CARET):
                    return False
                assert ann.type not in ann_resps, "{} are in response to annotation of same type {}".format(str(ann_resps[ann.type]), str(ann))
                assert len(ann_resps.keys()) <= 2, "ann {} has responses {} of more than two types".format(ann, ann_resps)
                
                other_ann_type = PDF_ANNOT_STRIKE_OUT if ann.type == PDF_ANNOT_CARET else PDF_ANNOT_CARET
                if not (other_ann_type in ann_resps and len(ann_resps[other_ann_type]) == 1):
                    return False
                other_ann = ann_resps[other_ann_type][0]

                return ann.rect.intersects(other_ann.rect) and other_ann.info['content'] == ''
                
            if is_replace_annot(annot, responses):
                annot.type = (None, 'Replace')

            def get_text(ann):
                


def draw_bounding_boxes(filename, annots):
    doc = pymupdf.open(filename)
    for pageno,page in enumerate(doc):
        for annot in annots[pageno]:
            if annot.type == PDF_ANNOT_TEXT:
                continue
            box = page.add_freetext_annot(annot.rect, '', text_color=(1,0,1))
            box.set_border(width=.5)
            box.update()
    doc.save('bounding_boxes.pdf')
        
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog = 'extannots.py',
                                     description = 'Extract annotations and comments from an annotated PDF as a .json file')
    parser.add_argument('filename')
    args = parser.parse_args()
    # doc = pymupdf.open(args.filename)
    filename = args.filename

    # annots = get_stable_annots(filename)

    get_corrections_annots(filename)
    
    # draw_bounding_boxes(filename, annots)

    # get_annots(doc)

    # for page in doc:
    #     for annot in page.annots():
    #         irtxref = annot.irt_xref

    #         print(annot)
    #         print(annot.rect)
    #         print("info: '{}'".format(annot.info))
    #         print("text in annotation rect: '{}'".format(page.get_textbox(annot.rect)))
    #         print("xref: '{}'".format(annot.xref))
    #         # print("responses: '{}'".format())

    #         if irtxref != 0:
    #             print("IRT_XREF: '{}'".format(irtxref))
    #         print()
    

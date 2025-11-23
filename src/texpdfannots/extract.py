import pymupdf
import argparse
import re
from copy import deepcopy

PDF_ANNOT_TEXT = (0, 'Text')
PDF_ANNOT_STRIKE_OUT = (11, 'StrikeOut')
PDF_ANNOT_CARET = (14, 'Caret')

CARET_BUFF = 2 # points
EXTRACT_TEXT_BUFFER_WIDTH = 2 # 2 pt

class Annot:
    """Revised version of pymupdf's Annot which fixes the bounding box of the Caret annotation and isn't fragile. See getStableAnnots()"""
    def __init__ (self, _pageno, _type, _info, _xref, _irt_xref, _rect, _intersecting_line_bb):
        self.pageno = _pageno        
        self.type = _type
        self.info = _info                
        self.xref = _xref
        self.irt_xref = _irt_xref
        self.rect = _rect
        self.intersecting_line_bb = _intersecting_line_bb
        
    def __str__ (self):
        return str({'pageno':self.pageno,'type':self.type,'info':self.info,'xref':self.xref,
                    'irt_xref':self.irt_xref,'rect':self.rect,'intersecting line bb':self.intersecting_line_bb})
    
    def __repr__ (self):
        return str(self)

class Edit:
    """
    Represents the information necessary to carry out an edit. An edit has the following attributes:
    
    "pageno":    page number in the PDF the annotation appears on
    
    "type":      annotation type
                 The Edit types are mostly a subset of the Annot types (full list at
                 https://pymupdf.readthedocs.io/en/latest/vars.html#annotationtypes) with the exception
                 of "Replace" which corresponds to the combination of a Strikeout and Caret annotation
                 which are identified by isReplaceAnnot in getCorrections(), not by pymupdf. 
    
    "message":   text in the annotation comment box and responses to it---typically edit directions
                 if it's not already self-evident from the type (e.g., Strikeout). The message itself
                 will contain one string for the original comment and a list of strings for the responses
    
    "selection": selected and surrounding text of the annotation from the PDF.

    Example
    {
      "pageno" : 1, 
      "type" : "Replace" 
      "message": {
                   "comment": "Equation (1)", 
                   "responses": ["COMP: pls link"]
                 }
      "selection": "Next we prove that <Replace>(1)</Replace> is a consequence of"
    }

    """
    def __init__ (self, _pageno, _type, _message, _selection):
        self.pageno = _pageno
        self.type = _type
        self.message = _message
        self.selection = _selection
        
    def __str__ (self):
        return str({'pageno':self.pageno,'type':self.type,'message':self.message,'selection':self.selection})
    
    def __repr__ (self):
        return str(self)

def getStableAnnots(doc, draw_boxes = False):
    """
    The bounding boxes of the original caret annotations often extend below the line they
    were inserted on, so they are resized to prevent that.

    pymupdf's annotations are also kind of fragile---they are strongly bound to the page they
    come from (so when the page goes away, so does the annotation), and I've encountered issues
    with using the provided methods to update the annotations, so I'll just store the
    annotations with my own class which isn't tied to the page and correctly stores the information.
    """
    stable_annots = {pageno:[] for pageno in range(len(doc))}
    for pageno, page in enumerate(doc):
        blocks = page.get_text('dict', sort=True)['blocks']
        line_bbs = [line['bbox'] for block in blocks for line in block['lines']]
        for annot in page.annots():
            annotRect = annot.rect
            intersecting_line_bbs = list(filter(lambda l: annotRect.intersects(l), line_bbs))

            if annot.type == PDF_ANNOT_TEXT:
                stable_annots[pageno].append(Annot(pageno,annot.type,annot.info,annot.xref,annot.irt_xref,annotRect,None))
                continue
            
            # bbbox = (x0, y0, x1, y1)
            highest_baseline_bb = sorted(intersecting_line_bbs, key = lambda bb : bb[3])[0]

            if annot.type == PDF_ANNOT_CARET: #fix caret rect
                raisedRect = pymupdf.Rect(annotRect.top_left, annotRect.bottom_right)
                raisedRect.y1 = highest_baseline_bb[3]
                annotRect = raisedRect

            stable_annots[pageno].append(Annot(pageno,annot.type,annot.info,annot.xref,annot.irt_xref,annotRect,highest_baseline_bb))

            if draw_boxes:               
                orig = page.add_freetext_annot(annotRect, "", text_color=(0,1,0))
                orig.set_border(width=.3)
                orig.update()                                       
            
                ah = page.add_freetext_annot(stable_annots[pageno][-1].rect, "", text_color=(0,0,1))
                ah.set_border(width=.3)
                ah.update() 

    if draw_boxes:
        doc.save('caret-isects.pdf')

    return stable_annots

def getAllResponses(stable_annots):
    """return dictionary where dict[xref] => [annots for which annot.irt_xref == xref]"""
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

def getResponses(annot, all_responses):
    """
    return dictionary where dict[type] =>
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

def getSelection(ann, doc):
    buff = EXTRACT_TEXT_BUFFER_WIDTH
    selection_name = ann.type[1]
    page = doc[ann.pageno]
    x0, y0, x1, y1 = ann.intersecting_line_bb
    
    if selection_name == 'Caret':
        insertion_point_x = ann.rect.x0 + ann.rect.width/2
        left_rect = pymupdf.Rect(x0, y0, insertion_point_x-CARET_BUFF, y1)
        right_rect = pymupdf.Rect(insertion_point_x+CARET_BUFF, y0, x1, y1)
        return '{left}<Caret></Caret>{right}'.format(left = page.get_textbox(left_rect),
                                                     right = page.get_textbox(right_rect))

    elif re.match('(?:Replace|StrikeOut|Highlight|Underline)', selection_name):
        left_rect = pymupdf.Rect(x0, y0, ann.rect.x0-buff, y1)
        middle_rect = pymupdf.Rect(ann.rect.x0+buff/2, y0, ann.rect.x1-buff/2, y1)
        # middle_rect = pymupdf.Rect(ann.rect.x0, y0, ann.rect.x1, y1)
        right_rect = pymupdf.Rect(ann.rect.x1+buff, y0, x1, y1)
        return '{left}<{name}>{middle}</{name}>{right}'.format(left = page.get_textbox(left_rect),
                                                               middle = page.get_textbox(middle_rect),
                                                               right = page.get_textbox(right_rect),
                                                               name = selection_name)
    else:
        return None
    

def getCorrections(filename):
    """return a list of Edits. See class Edit."""
    doc = pymupdf.open(filename)
    stable_annots = getStableAnnots(doc)
    all_responses = getAllResponses(stable_annots)
    
    corrections = []
    for pageno, page in enumerate(doc):
        for annot in stable_annots[pageno]: 
            if annot.irt_xref != 0:
                # only true for text responses and annotations which combine
                # with another to make an annotation of type 'Replace'
                continue
            responses = getResponses(annot, all_responses)
            text_responses = responses[PDF_ANNOT_TEXT] if PDF_ANNOT_TEXT in responses else []
            text_responses = [resp.info['content'] for resp in text_responses]
            message = {'comment': annot.info['content'], 'responses': text_responses}            

            def isReplaceAnnot(ann, ann_resps):
                if not (ann.type == PDF_ANNOT_STRIKE_OUT or ann.type == PDF_ANNOT_CARET) or ann_resps == []:
                    return False, None
                
                assert ann.type not in ann_resps, "{} are in response to annotation of same type {}".format(str(ann_resps[ann.type]), str(ann))
                assert len(ann_resps.keys()) <= 2, "ann {} has responses {} of more than two types".format(ann, ann_resps)
                
                other_ann_type = PDF_ANNOT_STRIKE_OUT if ann.type == PDF_ANNOT_CARET else PDF_ANNOT_CARET
                if not (other_ann_type in ann_resps and len(ann_resps[other_ann_type]) == 1):
                    return False, None
                other_ann = ann_resps[other_ann_type][0]

                return ann.rect.intersects(other_ann.rect) and other_ann.info['content'] == '', other_ann
                
            is_replace, other_ann = isReplaceAnnot(annot, responses)
            
            if is_replace:
                if annot.type[1] == 'Caret':
                    annot.rect = other_ann.rect
                annot.type = (None, 'Replace')

            selection_text = getSelection(annot, doc)

            corrections.append(Edit(annot.pageno, annot.type[1], message, selection_text))
                
    return corrections
            
if __name__ == '__main__':
    corrections = getCorrections('TeX/AnnotatedPDFS/ann0.pdf')
    for cor in corrections:
        print(cor)
        print()

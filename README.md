# Package management: pixi
Install pixi following the steps here: https://pixi.prefix.dev/latest/installation/

For my own record, here's what I did to set up the project environment. It's amazing how much simpler Pixi is than conda + poetry.
```shell
pixi init [project name] --format pyproject
pixi add python=3.12
pixi add [conda-forge available package]
pixi add --pypi [only-PyPi available package]
```

Pixi is a conda first manager, so it will import a package from conda-forge before anywhere else. If a package is not available in conda-forge, you can install it from PyPI, the python package index, which has a much lower barrier to entry and therefore many many more packages.

Oddly it looks like texsoup provided by conda-forge causes errors while texsoup downloaded from --pypi doesn't, so even though texsoup is recognized by conda-forge, I'm downloading it from pypi.

## Other dependencies
[diff-pdf](https://github.com/vslavik/diff-pdf)
pdflatex should be installed from TeX Live. I'm running texlive2023, and I may need to test that earlier distributions work, but I doubt they wont.

# Background and goal
Edits are specified to a source latex manuscript in the form of an annotated PDF of its output. Very often these edits are quite simple: text is inserted, removed, replaced, or repositioned. Other times they are more complicated---an equation, table, or figure needs to be repositioned or resized. 

# Overview
From my perspective automating corrections with an LLM is mostly a project of precise data extraction from the annotated PDF and the source latex so that the model is provided the most simple and clear input possible---the minimum and complete information required to carry out an individual edit.

This information should include
1. The type of edit 
1. The instruction and any responses to it 
1. The selected text (from the PDF)
1. The source code to be changed to carry out the edit

# Limitations 

## Multi-line selections
When an annotation selects text on more than one line, it's bounding box encompases all lines of selected text, no longer just the marked text (as it would be
if the text selected belonged to just one line).

To handle these cases I would need to
1. Identify highlight, strikeout, or other multi-select annotations whose bounding boxes include more than one line. (with pymupdf)
2. determine the bounding boxes of the actual annotation visual 

From what I can tell, the PDF does not contain the information necessary to determine (2). There's only one bounding box for an annotation and it is incorrect as discussed. It would not be extremely difficult to use some computer vision approach, even if it feels heavy handed. I'll probably use opencv for this when I get around to it.


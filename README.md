# Package and environment structure
I use conda for the virtual environment and poetry for package installation and dependency management.

## conda environment
Create the conda environment from `environment.yaml` with
```shell
conda env create -f environment.yaml
```
Activate and deactivate the environment with
```shell
conda activate texpdfannots
conda deactivate
```

Delete an environment with
```shell
conda remove --name [env name] --all
```

## python packages
After activating the conda environment, run
```shell
poetry install
```


# TODO
- Draw bounding boxes for text extraction
- may need to find size of adjacent letters


# Other Considerations

## Annotations that select text on more than one line
When an annotation selects text on more than one line, it's rectangle encompases all lines of selected text, no longer just the text itself (as it would be
if the text selected belonged to just one line).

To handle these cases I would need to
1. Identify highlight, strikeout, or other multi-select annotations whose bounding boxes include more than one line.
2. determine which line bounding boxes the annotation visual intersections with
3. Create the selected text "surrounding text <selected>text where the visual annotation intersects the line</selected> more surrounding

It's possible that 2. can be done by reading information from the PDF, but more likely I would need to process that region of the pdf as an image and
use some computer vision methods.


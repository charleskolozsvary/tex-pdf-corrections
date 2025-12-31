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

# Current limitations 

## Multi-line selections
When an annotation selects text on more than one line, it's bounding box encompases all lines of selected text, no longer just the marked text (as it would be
if the text selected belonged to just one line).

To handle these cases I would need to
1. Identify highlight, strikeout, or other multi-select annotations whose bounding boxes include more than one line. (with pymupdf)
2. determine the bounding boxes of the actual annotation visual 

From what I can tell, the PDF does not contain the information necessary to determine (2). There's only one bounding box for an annotation and it is incorrect as discussed. It would not be extremely difficult to use some computer vision approach, even if it feels heavy handed.


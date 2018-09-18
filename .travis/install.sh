#!/bin/bash
# Taken largely from https://stackoverflow.com/q/45257534
if [[ "$PYTHON_VERSION" == "2.7" ]]; then
    which virtualenv
    # Create and activate a virtualenv for conda
    virtualenv -p python condavenv
    source condavenv/bin/activate
    # Grab Miniconda 2
    wget https://repo.continuum.io/miniconda/Miniconda2-latest-MacOSX-x86_64.sh -O miniconda.sh
else
    # Install or upgrade to Python 3
    brew update 1>/dev/null
    # Simply upgrade if Python 2 has already been installed
    if brew info python@2 | grep -q "Python has been installed as"; then
        brew upgrade python
    else
        brew install python3
    fi
    # Create and activate a virtualenv for conda
    virtualenv -p python3 condavenv
    source condavenv/bin/activate
    # Grab Miniconda 3
    wget https://repo.continuum.io/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -O miniconda.sh
fi

# Install our version of miniconda
bash miniconda.sh -b -p $HOME/miniconda
# Modify the PATH, even though this doesn't seem to be effective later on
export PATH="$HOME/miniconda/bin:$PATH"
hash -r
# Configure conda to act non-interactively
conda config --set always_yes yes --set changeps1 no
# Update conda to the latest and greatest
conda update -q conda
# Enable conda-forge for binary packages, if necessary
conda config --add channels conda-forge
# Useful for debugging any issues with conda
conda info -a
echo "Creating conda virtualenv with Python $PYTHON_VERSION"
conda create -n venv python=$PYTHON_VERSION
# For whatever reason, source is not finding the activate script unless we
# specify the full path to it
source $HOME/miniconda/bin/activate venv
# This is the Python that will be used for running tests, so we dump its
# version here to help with troubleshooting
which python
python --version

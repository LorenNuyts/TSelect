from setuptools import setup, find_packages
from setuptools.extension import Extension
from Cython.Build import cythonize
import numpy as np

setup(
    name='tsfuse',
    version='2.0',
    packages=find_packages(),
    include_package_data=True,
    package_data={},
    setup_requires=[
        'setuptools',
        'Cython>=3.0.5',
        'numpy>=1.22.4'
    ],
    install_requires=[
        'six>=1.16.0',
        'graphviz>=0.20.1',
        'scipy>=1.10.1',
        'scikit-learn',
        'statsmodels>=0.14.0',
        'Pint>=0.21.1',
        'matplotlib==3.7.3',
        'pandas>=1.5.3',
        'sktime',
    ],
    extras_require={'test': [
        'pytest',
        'pandas>=0.24.2'
    ]},
    ext_modules=cythonize([
        Extension(
            'tsfuse.data.df', ['tsfuse/data/df.pyx'],
            include_dirs=[np.get_include()]
        ),
        Extension(
            'tsfuse.transformers.calculators.*', ['tsfuse/transformers/calculators/*.pyx'],
            include_dirs=[np.get_include()]
        ),
    ]),
)

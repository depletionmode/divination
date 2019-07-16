import setuptools

with open('README.md', 'r') as f:
    long_description = f.read()

setuptools.setup(
    name='divination',
    version='0.0.1',
    author='David Kaplan <@depletionmode>',
    description='Python module for iospace and physmem inspection on Windows',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/depletionmode/divination',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Win32"
        "Operation System :: Microsoft :: Windows :: Windows 10",
        "License :: OSI Approved :: MIT License"
    ]
)
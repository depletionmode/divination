import setuptools

with open('README.rst', 'r') as f:
    long_description = f.read()

setuptools.setup(
    name='divination',
    version='0.2.0',
    author='David Kaplan <@depletionmode>',
    description='Python module for hardware and physmem inspection',
    long_description=long_description,
    url='https://github.com/depletionmode/divination',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent"
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta"
    ]
)
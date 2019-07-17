import setuptools

with open('README.rst', 'r') as f:
    long_description = f.read()

setuptools.setup(
    name='divination',
    version='0.1.0',
    author='David Kaplan <@depletionmode>',
    description='Python module for iospace and physmem inspection on Windows',
    long_description=long_description,
    url='https://github.com/depletionmode/divination',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Win32 (MS Windows)",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta"
    ]
)
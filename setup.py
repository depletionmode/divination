import setuptools

with open('README.rst', 'r') as f:
    long_description = f.read()

setuptools.setup(
    name='divination',
    version='2.0.1',
    author='David Kaplan <@depletionmode>',
    description='Python module for hardware and physmem inspection',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    url='https://github.com/depletionmode/divination',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta"
    ],
    include_package_data=True
)

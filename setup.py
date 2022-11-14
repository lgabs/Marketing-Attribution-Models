from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()
    # substitute relative image path by absolute ones
    long_description = long_description.replace(
        "readme-images/",
        "https://raw.githubusercontent.com/DP6/Marketing-Attribution-Models/master/readme-images/",
    )

setup(
    name="marketing_attribution_models",
    version="1.1.0",
    description="Metodos de Atribuicao de Mídia",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Luan Gabriel (forked from andre.tocci@dp6.com.br)",
    author_email="luangabriel70@gmail.com",
    url="https://github.com/DP6/Marketing-Attribution-Models",
    packages=["marketing_attribution_models"],
    install_requires=[
        "numpy",
        "pandas",
        "matplotlib",
        "seaborn",
    ],
    license="Apache License 2.0",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.5",
)

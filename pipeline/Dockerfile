# Parent image
FROM ubuntu:18.04

# Certian installers have GUI's, this variable overide interactive installation.
ENV DEBIAN_FRONTEND=noninteractive

# Install system requirements
RUN ["apt", "update"]
RUN ["apt", "install", "-y", "gnupg2", "python3-pip", "software-properties-common", "git"]

# Ubuntu 18.04 repository doesn't include R(3.5.2). To fix this we need to add
# an external repository to install R from. First, we need to add GPG key:
RUN ["apt-key", "adv", "--keyserver", "keyserver.ubuntu.com", "--recv-keys", "E298A3A825C0D65DFD57CBB651716619E084DAB9"]
# Once we have the trusted key, we add the repository as follows:
RUN ["add-apt-repository", "deb https://cloud.r-project.org/bin/linux/ubuntu bionic-cran35/"]
RUN ["apt", "update"]
RUN ["apt", "install", "-y", "r-base"]
RUN ["apt", "install", "-y", "nodejs"]
RUN ["apt", "install", "-y", "vim"]


RUN ["useradd", "-ms", "/bin/bash", "beiwe-user"]
WORKDIR /home/beiwe-user

# Move the directory into the corresponding directory in the container
# ADD Beiwe-Analysis Beiwe-Analysis
ADD beiwe-backend beiwe-backend
RUN chown -R beiwe-user.beiwe-user beiwe-backend

# Install python requirements
USER beiwe-user
RUN ["pip3", "install", "--upgrade", "pip"]
RUN ["pip3", "install", "-r", "beiwe-backend/requirements.txt"]
RUN ["pip3", "install", "-r", "beiwe-backend/pipeline/Beiwe-Analysis/Pipeline/python3-requirements.txt"]
RUN ["pip3", "install", "jupyterlab"]
ENV PATH="/home/beiwe-user/.local/bin:${PATH}"

# Install R requirements
#RUN ["Rscript", "--vanilla", "beiwe-backend/pipeline/Beiwe-Analysis/Summary/install_required_packages.R"]

# setup jupyter lab
RUN ["openssl", "req", "-x509", "-nodes", "-days", "365", "-newkey", "rsa:2048", "-keyout", "mycert.pem", "-out", "mycert.pem", "-subj", "/C=US/ST=Texas/L=Austin/O=University of Texas at Austin/OU=Whole Communities Whole Health/CN=localhost"]
RUN ["jupyter", "lab", "--generate-config"]
RUN ["cp", "beiwe-backend/pipeline/jupyter_notebook_config.py", ".jupyter/jupyter_notebook_config.py"]

# Add Tini. Tini operates as a process subreaper for jupyter. This prevents kernel crashes.
ENV TINI_VERSION v0.6.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /home/beiwe-user/.local/bin/tini
USER root
RUN  chown beiwe-user.beiwe-user /home/beiwe-user/.local/bin/tini && chmod +x /home/beiwe-user/.local/bin/tini
USER beiwe-user
ENTRYPOINT ["/home/beiwe-user/.local/bin/tini", "--"]

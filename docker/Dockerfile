# QCADesigner-E command-line simulator (batch_sim) with the patch from this repository.
#
# Build (from the repository root):
#   docker build -t qde-batch -f docker/Dockerfile .
#
# Run the generator inside the container, with the repository mounted at /work:
#   docker run --rm -v "$PWD:/work" -w /work qde-batch \
#       python3 qca_scdd_dataset.py --qca layouts/LT_NAND.qca --cell Z --gate "LT NAND" \
#           --out runs/lt_nand --batch-sim batch_sim --resume
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential autoconf automake libtool pkg-config gettext intltool \
        libglib2.0-dev libgtk2.0-dev git ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/FSillT/QCADesigner-E.git /opt/QCADesigner-E
COPY qcadesigner_e_batch.patch /tmp/qcadesigner_e_batch.patch
WORKDIR /opt/QCADesigner-E
# Apply the patch, then make sure the shipped, pre-generated build files are newer than
# the patched Makefile.am so that make does not try to re-run automake.
RUN git apply /tmp/qcadesigner_e_batch.patch \
    && touch QCADesignerE/aclocal.m4 QCADesignerE/configure QCADesignerE/Makefile.in QCADesignerE/src/Makefile.in
WORKDIR /opt/QCADesigner-E/QCADesignerE
RUN sh ./configure && make -C src batch_sim
ENV PATH="/opt/QCADesigner-E/QCADesignerE/src:${PATH}"
CMD ["batch_sim"]

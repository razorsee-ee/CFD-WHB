#!/bin/bash
# OpenFOAM-14 (Foundation) binary package in a fresh Claude cloud container (Ubuntu, root). No source build.
#
#   bash tools/setup_openfoam14.sh > /tmp/setup_openfoam14.log 2>&1      (Bash run_in_background)
#   then: source /opt/of14env.sh
#
# dl.openfoam.org is often closed in the container, but its .deb files live on SourceForge
# (project "foam", foam/ubuntu/dists/<codename>/main/binary-amd64/), which is reachable.
# The script takes the newest openfoam14_<date>_amd64.deb for this Ubuntu release from the SourceForge
# file listing, checks its SHA-256 from the same listing, and installs it with apt
# (dependencies from the ordinary Ubuntu mirrors, --no-install-recommends: no ParaView/Qt).
# Measured 21.11.2026 (Ubuntu 24.04 container): download 126 MB in 11 s, SHA-256 OK,
# apt resolves 83 packages. The install itself was not run yet.
#
# Idempotent: re-running skips what is already done.
set -u
log() { echo "[of14 $(date +%H:%M:%S)] $*"; }
export DEBIAN_FRONTEND=noninteractive
ENV_FILE=/opt/of14env.sh
BASHRC=/opt/openfoam14/etc/bashrc

if [ -f "$BASHRC" ]; then
    log "OpenFOAM-14 already present"
else
    . /etc/os-release
    ARCH=$(dpkg --print-architecture)
    DIR=foam/ubuntu/dists/${VERSION_CODENAME}/main/binary-${ARCH}
    log "SourceForge listing $DIR"
    page=$(curl -fsSL -m 60 "https://sourceforge.net/projects/foam/files/$DIR/") \
        || { log "cannot read the SourceForge listing"; exit 1; }
    deb=$(echo "$page" | grep -oE "openfoam14_[0-9]{8}_${ARCH}\.deb" | sort -u | tail -1)
    [ -n "$deb" ] || { log "no openfoam14 package for $VERSION_CODENAME/$ARCH"; exit 1; }
    sha=$(echo "$page" | tr '{' '\n' | grep "\"name\":\"$deb\"" | grep -oE '"sha256":"[0-9a-f]{64}"' | cut -d'"' -f4)
    log "package $deb"
    curl -fsSL -m 1200 -o "/tmp/$deb" "https://downloads.sourceforge.net/project/foam/$DIR/$deb" \
        || { log "download failed"; exit 1; }
    if [ -n "$sha" ]; then
        echo "$sha  /tmp/$deb" | sha256sum -c --quiet - || { log "SHA-256 MISMATCH"; exit 1; }
        log "SHA-256 OK"
    else
        log "WARNING: no SHA-256 in the listing, not verified"
    fi
    apt-get update -qq > /tmp/apt_of14.log 2>&1
    apt-get install -y -qq --no-install-recommends "/tmp/$deb" >> /tmp/apt_of14.log 2>&1 \
        || { log "apt-get install failed, see /tmp/apt_of14.log"; tail -20 /tmp/apt_of14.log; exit 1; }
    log "installed in /opt/openfoam14"
fi

echo "source $BASHRC; export FOAM_SIGFPE=1; export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1" > $ENV_FILE
log "environment: source $ENV_FILE"

bash -c "source $ENV_FILE
echo OpenFOAM-\$WM_PROJECT_VERSION
for t in foamRun blockMesh snappyHexMesh surfaceFeatures checkMesh decomposePar reconstructPar \
         foamToVTK foamPostProcess foamListTimes foamDictionary mpirun; do
    command -v \$t > /dev/null || echo MISSING \$t
done
for l in lagrangianParcel multiphaseEuler incompressibleDenseParticleFluid multicomponentFluid; do
    ls \$FOAM_LIBBIN | grep -q \$l || echo MISSING lib\$l
done" && log "check finished (no MISSING lines above = ready)"

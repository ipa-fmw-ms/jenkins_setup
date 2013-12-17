#!/bin/bash
#export DIR="$(cd $(dirname $0); pwd -P)/chroot"

echo '---------------------------------'
echo '       Install TurboVNC'
echo '---------------------------------'
echo
~/jenkins-config/jenkins_setup/scripts/graphicTest/tvnc/installTurboVNC.bash

echo
echo
echo '---------------------------------'
echo '       Install VirtualGL'
echo '---------------------------------'
echo
~/jenkins-config/jenkins_setup/scripts/graphicTest/vgl/installVirtualGL.bash

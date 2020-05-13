#!/bin/bash

# ~/.profile: executed by the command interpreter for login shells.
# This file is not read by bash(1), if ~/.bash_profile or ~/.bash_login
# exists.
# see /usr/share/doc/bash/examples/startup-files for examples.
# the files are located in the bash-doc package.

# the default umask is set in /etc/profile; for setting the umask
# for ssh logins, install and configure the libpam-umask package.
#umask 022

alias update-commandline='cp ~/beiwe-backend/cluster_management/pushed_files/bash_profile.sh ~/.profile; cp ~/beiwe-backend/cluster_management/pushed_files/.inputrc ~/.inputrc'

#Alias aliases
alias p="nano ~/.profile; source ~/.profile"
alias up="source ~/.profile"

#File Sizes
alias duu="sudo du -d 1 -h | sort -h"

#Swap
alias createswap="sudo fallocate -l 4G /swapfile; sudo chmod 600 /swapfile; sudo mkswap /swapfile; sudo swapon /swapfile; swapon -s"
alias deleteswap="sudo swapoff /swapfile; sudo rm /swapfile"

#Bash Utility
alias sudo="sudo " # allows the use of all our aliases with the sudo command
alias n='nano -c'
alias no="nano -Iwn"
alias sn='sudo nano -c'
alias sno="sudo nano -Iwn"
alias ls='ls --color=auto'
alias la='ls -A'
alias ll='ls -lh'
alias lh='ls -lhX --color=auto'
alias lll="du -ah --max-depth=0 --block-size=MB --time * | sort -nr"
alias slll="sudo du -ah --max-depth=0 --block-size=MB --time * | sort -nr"
alias h="cd ~; clear; ls -X; echo"
alias grep='grep --color=auto'
alias g='grep -i'
alias u="cd .."
alias uu="cd ../.."
alias uuu="cd ../../.."
alias ri="rm -i"

#Tools with CL config
alias htop="htop -d 5"
alias nload="nload -a 5 -i 80000 -o 80000"
alias df="df -h"

#Git
alias s='git status'
alias gd='git diff'
alias gs='git diff --stat'
alias pull="git pull"
alias master="git checkout master"
alias prod="git checkout production"
alias dev='git checkout development'

#File locations
alias beiwe='cd $HOME/beiwe-backend'
alias apache="cd /etc/apache2"

#Apache restart functionality
alias apacherestart='sudo /etc/init.d/apache2 restart'
alias are='apacherestart'
alias restart='sudo service apache2 restart'
alias up='update'
alias update='cd $HOME/beiwe-backend; pyc; git pull; touch $HOME/beiwe-backend/wsgi.py'

alias pyc='find . -type f -name "*.pyc" -delete -print'

#supervisord (data processing)
alias processing-start="supervisord"
alias processing-stop="killall supervisord"
alias processing-restart="pkill -HUP supervisord"

#Logs
alias loga='tail -f /var/log/apache2/error.log | cut -d " " -f 4,10-' #tail follow apache log
alias logao='nano +1000000000 /var/log/apache2/error.log' #open log, go to end
alias logc='tail -f /var/log/celery/*'
alias logco='nano +1000000000 /var/log/celery/celeryd.err'
alias logd='tail -f /var/log/supervisor/*'
alias logdo='nano +1000000000 /var/log/supervisor/*'

#Configuration files
alias conf='sudo nano $HOME/beiwe-backend/config/settings.py'

#Services configuration files
alias boot="sudo sysv-rc-conf"

#Developer tools
alias db="cd $HOME/beiwe-backend/; python3 manage.py shell_plus"
alias py="python3"
alias ipy="ipython"
alias manage="python3 manage.py"
alias shell="python3 manage.py shell_plus"
alias ag="clear; printf '_%.0s' {1..100}; echo ''; echo 'Silver results begin here:'; ag --column"

function run {
    nohup python -u $1 > ~/$1_log.out &
}

function runloop ()
{
    while true; do
        $*;
        sleep 1;
    done
}


## Environment config ##

# uncomment for a colored prompt, if the terminal has the capability; turned
# off by default to not distract the user: the focus in a terminal window
# should be on the output of commands, not on the prompt
force_color_prompt=yes

# enable color support of ls and also add handy aliases
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto -h'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi


# if running bash
if [ -n "$BASH_VERSION" ]; then
    # include .bashrc if it exists
    if [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
    fi
fi

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

#makes the current git branch visible
function parse_git_branch () {
       git branch 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/ (\1)/'
}

RED="\[\033[0;31m\]"
YELLOW="\[\033[0;33m\]"
GREEN="\[\033[0;32m\]"
NO_COLOUR="\[\033[0m\]"
PS1="$GREEN\u$NO_COLOUR:\w$YELLOW\$(parse_git_branch)$NO_COLOUR\$ "



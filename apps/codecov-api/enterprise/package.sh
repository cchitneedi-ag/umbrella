#!/bin/sh
# Simple wrapper around pyinstaller
set -e
set -x

# Generate a random key for encryption
random_key=$(pwgen -s 16 1)

# Use the hacked ldd to fix libc.musl-x86_64.so.1 location
PATH="/pyinstaller:$PATH"

args_to_use=$(cat /pyinstaller/installer_args.txt)
echo $(find . -name "*.so")

mkdir src
echo 'true' > src/is_enterprise

# move migrations from app folders to api dir for sideloading. 
# cd /app
# find -type d | grep -i /migrations | sed 's|^./||' | xargs -i mkdir -p /app/dist/{}
# find -type f | grep -i /migrations/ | sed 's|^./||' | xargs -i cp -rf {} /app/dist/{}

# # Exclude pycrypto and PyInstaller from built packages
pyinstaller -F --debug=imports --exclude-module pycrypto --exclude-module PyInstaller --add-data src:/src --name api --clean --key $random_key ${args_to_use} ${pyinstaller_args} /app/manage.py

cat api.spec


# Clean up
cd /
rm -rf /home/*
rm -rf /hooks
mv -v app/dist/* /home
rm -rf /app
rm -rf /pyinstaller
rm -rf /usr/local/lib/python3.8/site-packages

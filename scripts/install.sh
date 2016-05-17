#!/usr/bin/env bash

set -ex
SCRIPT_DIR=$(dirname $0)
BASE_DIR=$(dirname $SCRIPT_DIR)
VENDOR_PATH=/srv/$PROJECT_NAME/vendor



# Load utilities
. $SCRIPT_DIR/utils.sh



# Install all the project dependencies.
echo 'Installing project dependencies'
sudo apt-get update
sudo apt-get install python3-dev build-essential libaio1 libpq-dev libgeos-dev -y
sudo apt-get install python-pip python3-pip unzip nginx -y
sudo pip install awscli

# Download, install, and configure Oracle Instant Client. Note that the EC2
# instance must have been created with a role that can read objects from S3.
#
# https://oracle-base.com/articles/misc/oracle-instant-client-installation
sudo mkdir -p $VENDOR_PATH/oracle
sudo chown `whoami`:`whoami` $VENDOR_PATH/oracle
aws s3 cp s3://ais-deploy/instantclient-basiclite-linux.x64-12.1.0.2.0.zip $VENDOR_PATH/oracle
aws s3 cp s3://ais-deploy/instantclient-sdk-linux.x64-12.1.0.2.0.zip $VENDOR_PATH/oracle
unzip $VENDOR_PATH/oracle/instantclient-basiclite-linux.x64-12.1.0.2.0.zip -d $VENDOR_PATH/oracle
unzip $VENDOR_PATH/oracle/instantclient-sdk-linux.x64-12.1.0.2.0.zip -d $VENDOR_PATH/oracle
ln -s libclntsh.so.12.1 $VENDOR_PATH/oracle/instantclient_12_1/libclntsh.so
cat >> ~/.bashrc <<EOF
export LD_LIBRARY_PATH=$VENDOR_PATH/oracle/instantclient_12_1:\$LD_LIBRARY_PATH
export PATH=\$PATH:$VENDOR_PATH/oracle/instantclient_12_1
EOF
export LD_LIBRARY_PATH=$VENDOR_PATH/oracle/instantclient_12_1:$LD_LIBRARY_PATH
export PATH=$PATH:$VENDOR_PATH/oracle/instantclient_12_1

# Download and install the private key for installing passyunk
if ! test -f /etc/ssh/github ; then
    aws s3 cp s3://ais-deploy/github ~/.ssh
    sudo bash <<EOF
        mv ~/.ssh/github /etc/ssh/
        chmod 600 /etc/ssh/github
EOF
fi

# Load the GitHub private key and install passyunk
sudo bash <<EOF
    eval `ssh-agent -s`
    ssh-add /etc/ssh/github
    ssh-keyscan -H github.com | sudo tee /etc/ssh/ssh_known_hosts

    pip3 install -e git+ssh://github.com/CityOfPhiladelphia/passyunk.git#egg=passyunk
EOF

# Install python requirements on python3 with library paths
sudo LD_LIBRARY_PATH=$LD_LIBRARY_PATH pip3 install --requirement requirements.txt


# # Configure the AWS CLI
# echo 'Configuring AWS CLI'
# mkdir -p ~/.aws
# cat > ~/.aws/config <<EOF
# [default]
# aws_access_key_id = $AWS_ID
# aws_secret_access_key = $AWS_SECRET
# output = text
# region = us-east-1
# EOF




# Run any management commands for migration, static files, etc.



# Set up the web server
sudo honcho export upstart /etc/init \
    --app $PROJECT_NAME \
    --user nobody \
    --procfile $BASE_DIR/Procfile

# Set up nginx
# https://docs.getsentry.com/on-premise/server/installation/#proxying-with-nginx
echo "$(generate_nginx_conf_nossl)" | sudo tee /etc/nginx/sites-available/$PROJECT_NAME
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -fs /etc/nginx/sites-available/$PROJECT_NAME /etc/nginx/sites-enabled/$PROJECT_NAME

# Re/start the web server
sudo service $PROJECT_NAME restart
sudo service nginx reload
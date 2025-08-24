set -e
PERSISTENT_DIR=/data/persistent/
DB_PATH=/data/persistent/db.sqlite3; 
PROJECT_DIR=/var/www/yatbc; 
chmod -R 755 /data/persistent

VERSION=$(cat $PROJECT_DIR/tor/templates/includes/version.html)
echo "Preparing YATBC version: $VERSION"
mkdir -p $PERSISTENT_DIR/queue
if [ ! -f $DB_PATH ]; then
    echo 'Database not found. Preparing for first run...';
    . /var/venv_django/bin/activate; 
    DJANGO_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')        
    ARIA_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(10))')
    printf 'export DJANGO_SECRET_KEY="%s"\nexport ARIA_SECRET_KEY="%s"\nexport TZ="%s"\n' "$DJANGO_SECRET" "$ARIA_SECRET" "$TZ" > $PERSISTENT_DIR/.env
    . $PERSISTENT_DIR/.env
    
    python3 $PROJECT_DIR/manage.py migrate;
    python3 $PROJECT_DIR/manage.py collectstatic --noinput;          
    mkdir -p $PERSISTENT_DIR/aria2/logs
    mkdir -p $PERSISTENT_DIR/http
    mkdir -p $PERSISTENT_DIR/apache/logs
    chmod -R 755 $PERSISTENT_DIR                              
    
    cp /etc/aria2.conf $PERSISTENT_DIR/aria2/aria2.conf
    sed -i 's/rpc-secret=docker-compose-will-replace/rpc-secret='$ARIA_SECRET'/g' $PERSISTENT_DIR/aria2/aria2.conf

    
    
    echo 'Application preparation done.';
else          
    echo 'Performing application maintenance...';
    . /var/venv_django/bin/activate;      
    . $PERSISTENT_DIR/.env
    python3 $PROJECT_DIR/manage.py migrate;
    python3 $PROJECT_DIR/manage.py collectstatic --noinput;          
    python3 $PROJECT_DIR/manage.py prune_db_task_results;         
fi;  
echo "YATBC version: $VERSION, prepared"
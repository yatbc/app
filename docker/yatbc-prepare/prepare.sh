set -e
DB_PATH=/data/persistent/db.sqlite3; 
PROJECT_DIR=/var/www/yatbc; 
chmod -R 755 /data/persistent

VERSION=$(cat $PROJECT_DIR/tor/templates/includes/version.html)
echo "Preparing YATBC version: $VERSION"
if [ ! -f $DB_PATH ]; then
    echo 'Database not found. Preparing for first run...';
    . /var/venv_django/bin/activate; 
    DJANGO_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')        
    ARIA_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(10))')
    printf 'export DJANGO_SECRET_KEY="%s"\nexport ARIA_SECRET_KEY="%s"\nexport TZ="%s"\n' "$DJANGO_SECRET" "$ARIA_SECRET" "$TZ" > /data/persistent/.env
    . /data/persistent/.env
    
    python3 $PROJECT_DIR/manage.py migrate;
    python3 $PROJECT_DIR/manage.py collectstatic --noinput;          
    mkdir -p /data/persistent/aria2/logs
    mkdir -p /data/persistent/http
    mkdir -p /data/persistent/apache/logs
    chmod -R 755 /data/persistent/                              
    
    cp /etc/aria2.conf /data/persistent/aria2/aria2.conf
    sed -i 's/rpc-secret=docker-compose-will-replace/rpc-secret='$ARIA_SECRET'/g' /data/persistent/aria2/aria2.conf

    
    
    echo 'Application preparation done.';
else          
    echo 'Performing application maintenance...';
    . /var/venv_django/bin/activate;      
    . /data/persistent/.env
    python3 $PROJECT_DIR/manage.py migrate;
    python3 $PROJECT_DIR/manage.py collectstatic --noinput;          
    python3 $PROJECT_DIR/manage.py prune_db_task_results;         
fi;  
echo "YATBC version: $VERSION, prepared"
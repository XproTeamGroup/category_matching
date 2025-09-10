#!/bin/bash
DOMAIN="cms.xpro.com.ua"
URL="https://cms.xpro.com.ua/api/public/listCategories?page=1&limit=100"

echo "=== 🔎 Проверка DNS для $DOMAIN ==="
nslookup $DOMAIN || dig $DOMAIN

echo -e "\n=== 🌐 Проверка ping до $DOMAIN ==="
ping -c 4 $DOMAIN

echo -e "\n=== 🛣️  Проверка traceroute до $DOMAIN ==="
traceroute $DOMAIN || tracepath $DOMAIN

echo -e "\n=== 🔒 Проверка SSL-сертификата $DOMAIN ==="
echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | openssl x509 -noout -dates -issuer -subject

echo -e "\n=== 🚪 Проверка открытости порта 443 ==="
nc -zv $DOMAIN 443

echo -e "\n=== 📡 Проверка curl (с заголовками) ==="
curl -vkI $URL --max-time 15

#!/etc/bash

#11.20
del_rubbish(){
    python -c "from function import *;down_db.delete_many({});"
}

#2019.01.10
update_sp(){
    ps -aux | grep supervisord | awk '{print "kill -9 " $2}'|sh
    rm -rf supervisord.conf
    cp supervisord.conf.sample supervisord.conf
    supervisord -c supervisord.conf
}

#2019.01.18
update_config(){
    num=`cat config.py | grep "show_secret" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'show_secret="no"' >> config.py
    fi

    num=`cat config.py | grep "encrypt_file" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'encrypt_file="no"' >> config.py
    fi

    num=`cat config.py | grep "headCode" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'headCode=""""""' >> config.py
    fi

    num=`cat config.py | grep "footCode" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'footCode=""""""' >> config.py
    fi

    num=`cat config.py | grep "cssCode" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'cssCode=""""""' >> config.py
    fi

    num=`cat config.py | grep "title_pre" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'title_pre=""' >> config.py
    fi

    num=`cat config.py | grep "theme" | wc -l`
    if [ $num == 0 ]; then
        echo '' >> config.py
        echo 'theme="material"' >> config.py
    fi

}

restart(){
    supervisorctl -c supervisord.conf restart pyone
}

#执行
echo "2018.11.20更新版本，修复了磁力链接下载的bug&上传、展示有特殊字符的文件出问题的bug。"
echo "2018.11.21更新版本，优化磁力下载功能-可选下载文件。"
echo "2018.12.04更新版本，优化磁力下载界面"
echo "2018.12.10更新版本，修复特定分享目录后，二级目录设置密码出错的bug"
echo "2018.12.20更新版本，基础设置之后无需重启网站啦！如果你一直有保存之后不生效的问题，那么本次直接重启服务器吧！"
echo "2019.01.10更新版本，1. 修复防盗链失效的bug；2. 优化开机启动脚本。"
echo "2019.01.13更新版本，修复后台修改密码不生效的bug"
echo "2019.01.14更新版本，修复bug"
echo "2019.01.18更新版本，修复bug；添加搜索功能"
echo "2019.01.21更新版本，添加功能：后台直接添加盘符...避免小白添加配置出现各种问题"
echo "2019.01.23更新版本：修复设置了共享目录后设置README/HEAD/密码出错的bug;优化更新文件列表假死的bug"
echo "2019.01.24更新版本：支持设置加密文件夹下的文件；优化UI"
echo "2019.01.28更新版本：支持自定义代码！"
echo "2019.01.29更新版本：支持设置网站标题前缀；支持自定义主题（待更新设计标准）"
update_config
restart
echo "---------------------------------------------------------------"
echo "更新完成！"
echo "如果网站无法访问，请检查config.py!"
echo "---------------------------------------------------------------"
echo
echo "PyOne交流群：864996565"


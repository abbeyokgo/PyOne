#-*- coding=utf-8 -*-
from __future__ import print_function
import eventlet
eventlet.monkey_patch()
from flask import Blueprint,redirect,url_for,request,render_template,flash,session,jsonify,Response,make_response
from flask_sqlalchemy import Pagination
from function import *
from config import *
from run import FetchData,path_list,GetName,CodeType,_remote_content,rd,has_item,AddResource
import os
import io
import re
import subprocess
import random
import urllib
from shelljob import proc



admin = Blueprint('admin', __name__,url_prefix='/admin')

############功能函数
def set(key,value,user='A'):
    allow_key=['title','downloadUrl_timeout','allow_site','password','client_secret','client_id','share_path','other_name','tj_code','ARIA2_HOST','ARIA2_PORT','ARIA2_SECRET','ARIA2_SCHEME']
    if key not in allow_key:
        return u'禁止修改'
    print('set {}:{}'.format(key,value))
    config_path=os.path.join(config_dir,'config.py')
    with open(config_path,'r') as f:
        old_text=f.read()
    with open(config_path,'w') as f:
        if key in ['client_secret','client_id','share_path','other_name']:
            old_kv=re.findall('"{}":{{[\w\W]*}}'.format(user),old_text)[0]
            new_kv=re.sub('"{}":.*?,'.format(key),'"{}":"{}",'.format(key,value),old_kv,1)
            new_text=old_text.replace(old_kv,new_kv,1)
        elif key=='allow_site':
            value=value.split(',')
            new_text=re.sub('{}=.*'.format(key),'{}={}'.format(key,value),old_text)
        elif key=='tj_code':
            new_text=re.sub('{}=.*'.format(key),'{}="""{}"""'.format(key,value),old_text)
        else:
            new_text=re.sub('{}=.*'.format(key),'{}="{}"'.format(key,value),old_text)
        f.write(new_text)


############视图函数
@admin.before_request
def before_request():
    if request.endpoint.startswith('admin') and request.endpoint!='admin.login' and session.get('login') is None: #and request.endpoint!='admin.install'
        return redirect(url_for('admin.login'))


########web console
@admin.route('/web_console')
def web_console():
    g = proc.Group()
    action=request.args.get('action')
    allow_action=['UpdateFile','UploadDir','Upload']
    if action not in allow_action:
        return make_response('error')
    if action in ['UploadDir','Upload']:
        local=urllib.unquote(request.args.get('local'))
        remote=urllib.unquote(request.args.get('remote'))
        user=urllib.unquote(request.args.get('user'))
        cmd=["python","-u",os.path.join(config_dir,'function.py'),action,local,remote,user]
    elif action=='UpdateFile':
        type_=request.args.get('type')
        cmd=["python","-u",os.path.join(config_dir,'function.py'),'UpdateFile',type_]
    else:
        cmd=["python","-u",os.path.join(config_dir,'function.py'),action]
    p = g.run(cmd)
    def read_process():
        while g.is_pending():
            lines = g.readlines()
            for proc, line in lines:
                yield "data:" + line + "\n\n"
        yield "data:end\n\n"
    return Response(read_process(), mimetype= 'text/event-stream')

########admin
@admin.route('/',methods=['GET','POST'])
@admin.route('/setting',methods=['GET','POST'])
def setting():
    if request.method=='POST':
        title=request.form.get('title','PyOne')
        downloadUrl_timeout=request.form.get('downloadUrl_timeout',5*60)
        allow_site=request.form.get('allow_site','no-referrer')
        tj_code=request.form.get('tj_code','')
        ARIA2_HOST=request.form.get('ARIA2_HOST','localhost').replace('https://','').replace('http://','')
        ARIA2_PORT=request.form.get('ARIA2_PORT',6800)
        ARIA2_SECRET=request.form.get('ARIA2_SECRET','')
        ARIA2_SCHEME=request.form.get('ARIA2_SCHEME','http')
        password1=request.form.get('password1')
        password2=request.form.get('password2')
        new_password=password
        if ((password1 is not None and password2 is None) or (password1 is None and password2 is not None)):
            flash(u'请输入新密码或者二次确认新密码')
        elif password1 is not None and password2 is not None and password1!=password2:
            flash(u'两次输入密码不相同')
        elif password1 is not None and password2 is not None and password1==password2 and password1!='':
            new_password=password1
        set('title',title)
        set('downloadUrl_timeout',downloadUrl_timeout)
        set('allow_site',allow_site)
        set('tj_code',tj_code)
        set('ARIA2_HOST',ARIA2_HOST)
        set('ARIA2_PORT',ARIA2_PORT)
        set('ARIA2_SECRET',ARIA2_SECRET)
        set('ARIA2_SCHEME',ARIA2_SCHEME)
        set('password',new_password)
        ####网盘信息处理
        for k,v in request.form.to_dict().items():
            if 'share_path' in k or 'other_name' in k:
                user=re.findall('\[(.*?)\]',k)[0]
                key=re.findall('(.*)\[',k)[0]
                print('setting {}\'s {}\'s value {}'.format(user,key,v))
                set(key,v,user)
        reload()
        return render_template('admin/setting.html')
    return render_template('admin/setting.html')




@admin.route('/upload',methods=["POST","GET"])
def upload():
    if request.method=='POST':
        user=request.form.get('user').encode('utf-8')
        local=request.form.get('local').encode('utf-8')
        remote=request.form.get('remote').encode('utf-8')
        if not os.path.exists(local):
            flash('本地目录/文件不存在')
            return redirect(url_for('admin.upload'))
        if os.path.isfile(local):
            action='Upload'
        else:
            action='UploadDir'
        return render_template('admin/upload.html',remote=remote,local=local,action=action,user=user)
    return render_template('admin/upload.html')



@admin.route('/cache',methods=["POST","GET"])
def cache():
    if request.method=='POST':
        type=request.form.get('type')
        return render_template('admin/cache.html',type=type,action='UpdateFile')
    return render_template('admin/cache.html')


@admin.route('/manage',methods=["POST","GET"])
def manage():
    if request.method=='POST':
        pass
    path=urllib.unquote(request.args.get('path','A:/'))
    user,n_path=path.split(':')
    if n_path=='':
        path=':'.join([user,'/'])
    page=request.args.get('page',1,type=int)
    image_mode=request.args.get('image_mode')
    sortby=request.args.get('sortby')
    order=request.args.get('order')
    if sortby:
        sortby=request.args.get('sortby')
    else:
        sortby=request.cookies.get('admin_sortby') if request.cookies.get('admin_sortby') is not None else 'lastModtime'
        sortby=sortby
    if order:
        order=request.args.get('order')
    else:
        order=request.cookies.get('admin_order') if request.cookies.get('admin_order') is not None else 'desc'
        order=order
    resp,total = FetchData(path=path,page=page,per_page=50,sortby=sortby,order=order)
    pagination=Pagination(query=None,page=page, per_page=50, total=total, items=None)
    if path.split(':',1)[-1]=='/':
        path=':'.join([path.split(':',1)[0],''])
    resp=make_response(render_template('admin/manage.html',pagination=pagination,items=resp,path=path,sortby=sortby,order=order,cur_user=user,endpoint='admin.manage'))
    resp.set_cookie('admin_sortby',str(sortby))
    resp.set_cookie('admin_order',str(order))
    return resp


@admin.route('/edit',methods=["GET","POST"])
def edit():
    if request.method=='POST':
        fileid=request.form.get('fileid')
        user=request.form.get('user')
        content=request.form.get('content').encode('utf-8')
        info={}
        token=GetToken(user=user)
        app_url=GetAppUrl()
        headers={'Authorization':'bearer {}'.format(token)}
        url=app_url+'v1.0/me/drive/items/{}/content'.format(fileid)
        try:
            r=requests.put(url,headers=headers,data=content,timeout=10)
            data=json.loads(r.content)
            if data.get('id'):
                info['status']=0
                info['msg']='修改成功'
                rd.delete('{}:content'.format(fileid))
                file=items.find_one({'id':fileid})
                name=file['name']
                path=file['path'].replace(name,'',1)
                if len(path.split('/'))>2 and path.split('/')[-1]=='':
                    path=path[:-1]
                # if path=='':
                #     path='/'
                # if not path.startswith('/'):
                #     path='/'+path
                # path='{}:{}'.format(user,path)
                key='has_item$#$#$#$#{}$#$#$#$#{}'.format(path,name)
                print('edit key:{}'.format(key))
                rd.delete(key)
            else:
                info['status']=0
                info['msg']=data.get('error').get('message')
        except Exception as e:
            print(e)
            info['status']=0
            info['msg']='修改超时'
        return jsonify(info)
    fileid=request.args.get('fileid')
    user=request.args.get('user')
    name=GetName(fileid)
    ext=name.split('.')[-1]
    language=CodeType(ext)
    if language is None:
        language='Text'
    content=_remote_content(fileid,user)
    return render_template('admin/edit.html',content=content,fileid=fileid,name=name,language=language,cur_user=user)

###本地上传文件只onedrive，通过服务器中转
@admin.route('/upload_local',methods=['POST','GET'])
def upload_local():
    user,remote_folder=request.args.get('path').split(':')
    return render_template('admin/upload_local.html',remote_folder=remote_folder,cur_user=user)

@admin.route('/checkChunk', methods=['POST'])
def checkChunk():
    md5=request.form.get('fileMd5')
    fileName=request.form.get('name').encode('utf-8')
    chunk=request.form.get('chunk',0,type=int)
    filename = u'./upload/{}-{}'.format(fileName, chunk)
    if os.path.exists(filename):
        exists=True
    else:
        exists=False
    return jsonify({'ifExist':exists})


@admin.route('/mergeChunks', methods=['POST'])
def mergeChunks():
    fileName=request.form.get('fileName').encode('utf-8')
    md5=request.form.get('fileMd5')
    chunk = 0  # 分片序号
    with open(u'./upload/{}'.format(fileName), 'wb') as target_file:  # 创建新文件
        while True:
            try:
                filename = u'./upload/{}-{}'.format(fileName, chunk)
                source_file = open(filename, 'rb')  # 按序打开每个分片
                target_file.write(source_file.read())  # 读取分片内容写入新文件
                source_file.close()
            except IOError as msg:
                break
            chunk += 1
            os.remove(filename)  # 删除该分片，节约空间
    return jsonify({'upload':True})


@admin.route('/recv_upload', methods=['POST'])
def recv_upload():  # 接收前端上传的一个分片
    md5=request.form.get('fileMd5')
    name=request.form.get('name').encode('utf-8')
    chunk_id=request.form.get('chunk',0,type=int)
    filename = '{}-{}'.format(name,chunk_id)
    upload_file = request.files['file']
    upload_file.save(u'./upload/{}'.format(filename))
    return jsonify({'upload_part':True})


@admin.route('/to_one',methods=['GET'])
def server_to_one():
    user=request.args.get('user')
    filename=request.args.get('filename').encode('utf-8')
    remote_folder=request.args.get('remote_folder').encode('utf-8')
    if remote_folder!='/':
        remote_folder=remote_folder+'/'
    local_dir=os.path.join(config_dir,'upload')
    filepath=urllib.unquote(os.path.join(local_dir,filename))
    _upload_session=Upload_for_server(filepath,remote_folder,user)
    def read_status():
        while True:
            try:
                msg=_upload_session.next()['status']
                yield "data:" + msg + "\n\n"
            except Exception as e:
                msg='end'
                yield "data:" + msg + "\n\n"
                os.remove(filepath)
                break
    return Response(read_status(), mimetype= 'text/event-stream')



###本地上传文件只onedrive，通过服务器中转
@admin.route('/setFile',methods=["GET","POST"])
@admin.route('/setFile/<filename>',methods=["GET","POST"])
def setFile(filename=None):
    if request.method=='POST':
        path=request.form.get('path')
        if path.split(':')[-1]=='':
            path=path.split(':')[0]+':/'
        user,n_path=path.split(':')
        filename=request.form.get('filename')
        if not n_path.startswith('/'):
            n_path='/'+n_path
        share_path=od_users.get(user).get('share_path')
        if share_path!='/':
            remote_file=os.path.join(os.path.join(share_path,n_path),filename)
        else:
            remote_file=os.path.join(n_path,filename)
        content=request.form.get('content').encode('utf-8')
        info={}
        token=GetToken(user=user)
        app_url=GetAppUrl()
        headers={'Authorization':'bearer {}'.format(token)}
        url=app_url+'v1.0/me/drive/items/root:{}:/content'.format(remote_file)
        try:
            r=requests.put(url,headers=headers,data=content,timeout=10)
            data=json.loads(r.content)
            if data.get('id'):
                AddResource(data,user)
                info['status']=0
                info['msg']='添加成功'
                key='has_item$#$#$#$#{}$#$#$#$#{}'.format(path,filename)
                print('set key:{}'.format(key))
                rd.delete(key)
            else:
                info['status']=0
                info['msg']=data.get('error').get('message')
        except Exception as e:
            info['status']=0
            info['msg']='超时'
        return jsonify(info)
    path=urllib.unquote(request.args.get('path'))
    if path.split(':')[-1]=='':
        path=path.split(':')[0]+':/'
    user,n_path=path.split(':')
    _,fid,i=has_item(path,filename)
    if fid!=False:
        return redirect(url_for('admin.edit',fileid=fid,user=user))
    return render_template('admin/setpass.html',path=path,filename=filename,cur_user=user)


@admin.route('/delete',methods=["POST"])
def delete():
    ids=request.form.get('id')
    user=request.form.get('user')
    if ids is None:
        return jsonify({'msg':u'请选择要删除的文件','status':0})
    ids=ids.split('##')
    infos={}
    infos['status']=1
    infos['delete']=0
    infos['fail']=0
    for id in ids:
        print('delete {}'.format(id))
        file=items.find_one({'id':id})
        name=file['name']
        path=file['path'].replace(name,'')
        if len(path.split('/'))>2 and path.split('/')[-1]=='':
            path=path[:-1]
        key='has_item$#$#$#$#{}$#$#$#$#{}'.format(path,name)
        print('delete key:{}'.format(key))
        rd.delete(key)
        kc='{}:content'.format(id)
        rd.delete(kc)
        status=DeleteRemoteFile(id,user)
        if status:
            infos['delete']+=1
        else:
            infos['fail']+=1
    return jsonify(infos)


@admin.route('/add_folder',methods=['POST'])
def AddFolder():
    folder_name=request.form.get('folder_name')
    path=request.args.get('path')
    user,grand_path=path.split(':')
    if grand_path=='' or grand_path is None:
        grand_path='/'
    else:
        if grand_path.startswith('/'):
            grand_path=grand_path[1:]
    result=CreateFolder(folder_name,grand_path,user)
    return jsonify({'result':result})

@admin.route('/move_file',methods=['POST'])
def MoveFileToNewFolder():
    fileid=request.form.get('fileid')
    user=request.form.get('user')
    new_folder_path=request.form.get('new_folder_path')
    if new_folder_path=='' or new_folder_path is None:
        new_folder_path='/'
    else:
        if new_folder_path.startswith('/'):
            new_folder_path=new_folder_path[1:]
    result=MoveFile(fileid,new_folder_path,user)
    return jsonify({'result':result})

######离线下载---调用aria2
@admin.route('/off_download',methods=['POST','GET'])
def off_download():
    if request.method=='POST':
        p,status=get_aria2()
        if not status:
            return jsonify({'status':False,'msg':p})
        urls=request.form.get('urls').split('\n')
        grand_path=request.form.get('grand_path')
        user=request.form.get('user')
        for url in urls:
            if url.strip()!='':
                cmd=u'python {} download_and_upload "{}" "{}" {}'.format(os.path.join(config_dir,'function.py'),url,grand_path,user)
                subprocess.Popen(cmd,shell=True)
        return jsonify({'status':True,'msg':'ok'})
    path=request.args.get('path')
    user,grand_path=path.split(':')
    return render_template('admin/offdownload.html',grand_path=grand_path,cur_user=user)


@admin.route('/jsonrpc',methods=['POST'])
def RPCserver():
    action=request.form.get('action')
    allow_action=['tellActive','tellSuccess','tellFail','tellUnselected','pause','pauseAll','unpause','unpauseAll','remove','removeAll','restart','unselected','selected']
    action_dict=dict(tellActive=1,tellSuccess=0,tellFail=-1,tellUnselected=2)
    if action not in allow_action:
        return jsonify({'code':0,'msg':'not allow action'})
    if action in ['tellActive','tellSuccess','tellFail','tellUnselected']:
        status=action_dict[action]
        ret={'code':1,'msg':'get data success','result':get_tasks(status)}
    elif action in ['pause','pauseAll','unpause','unpauseAll','remove','removeAll','restart','unselected','selected']:
        ret=None
        gids=request.form.get('gid').split('####')
        ret1=Aria2Method(action=action,gids=gids)
        ret2=DBMethod(action=action,gids=gids)
        if ret1 is not None:
            ret=ret1
        else:
            ret=ret2
    return jsonify(ret)


@admin.route('/login',methods=["POST","GET"])
def login():
    if request.method=='POST':
        password1=request.form.get('password')
        if password1==password:
            session['login']='true'
            if len(os.listdir(os.path.join(config_dir,'data')))<=1:
                return redirect(url_for('admin.install',step=0,user='A'))
            return redirect(url_for('admin.setting'))
        else:
            return render_template('admin/login.html')
    return render_template('admin/login.html')


@admin.route('/logout',methods=['GET','POST'])
def logout():
    session.pop('login',None)
    return redirect('/')

@admin.route('/reload',methods=['GET','POST'])
def reload():
    cmd='supervisorctl -c {} restart pyone'.format(os.path.join(config_dir,'supervisord.conf'))
    subprocess.Popen(cmd,shell=True)
    flash('正在重启网站...如果更改了分享目录，请更新缓存')
    return redirect(url_for('admin.setting'))

###########################################安装
@admin.route('/install',methods=['POST','GET'])
def install():
    if request.method=='POST':
        step=request.form.get('step',type=int)
        user=request.form.get('user')
        if step==1:
            client_secret=request.form.get('client_secret')
            client_id=request.form.get('client_id')
            set('client_secret',client_secret,user)
            set('client_id',client_id,user)
            login_url=LoginUrl.format(client_id=client_id,redirect_uri=redirect_uri)
            return render_template('admin/install_1.html',client_secret=client_secret,client_id=client_id,login_url=login_url,cur_user=user)
        else:
            client_secret=request.form.get('client_secret')
            client_id=request.form.get('client_id')
            code=request.form.get('code')
            #授权
            headers['Content-Type']='application/x-www-form-urlencoded'
            data=AuthData.format(client_id=client_id,redirect_uri=urllib.quote(redirect_uri),client_secret=client_secret,code=code)
            url=OAuthUrl
            r=requests.post(url,data=data,headers=headers)
            Atoken=json.loads(r.text)
            if Atoken.get('access_token'):
                with open(os.path.join(config_dir,'data/{}_Atoken.json'.format(user)),'w') as f:
                    json.dump(Atoken,f,ensure_ascii=False)
                refresh_token=Atoken.get('refresh_token')
                token=ReFreshToken(refresh_token,user)
                with open(os.path.join(config_dir,'data/{}_token.json'.format(user)),'w') as f:
                    json.dump(token,f,ensure_ascii=False)
                return make_response('<h1>授权成功!<a href="/?t={}">点击进入首页</a><br>请先在<B>后台-页面缓存</B>，运行更新数据操作<！/h1>'.format(time.time()))
            else:
                return jsonify(Atoken)
    step=request.args.get('step',type=int)
    user=request.args.get('user','A')
    resp=render_template('admin/install_0.html',step=step,cur_user=user,redirectUrl=redirect_uri)
    return resp



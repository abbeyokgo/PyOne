#-*- coding=utf-8 -*-
from base_view import *
import subprocess



@admin.route('/manage',methods=["POST","GET"])
def manage():
    if request.method=='POST':
        pass
    path=urllib.unquote(request.args.get('path','{}:/'.format(GetConfig('default_pan'))))
    if path=='':
        path='{}:/'.format(GetConfig('default_pan'))
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
    resp=MakeResponse(render_template('admin/manage/manage.html',pagination=pagination,items=resp,path=path,sortby=sortby,order=order,cur_user=user,endpoint='admin.manage'))
    resp.set_cookie('admin_sortby',str(sortby))
    resp.set_cookie('admin_order',str(order))
    return resp


@admin.route('/edit',methods=["GET","POST"])
def edit():
    if request.method=='POST':
        fileid=request.form.get('fileid')
        user=request.form.get('user')
        content=request.form.get('content').encode('utf-8')
        info=EditFile(fileid=fileid,content=content,user=user)
        return jsonify(info)
    fileid=request.args.get('fileid')
    user=request.args.get('user')
    name=GetName(fileid)
    ext=name.split('.')[-1]
    language=CodeType(ext)
    if language is None:
        language='Text'
    content=common._remote_content(fileid,user)
    resp=MakeResponse(render_template('admin/setFile/edit.html',content=content,fileid=fileid,name=name,language=language,cur_user=user))
    return resp

###本地上传文件只onedrive，通过服务器中转
@admin.route('/upload_local',methods=['POST','GET'])
def upload_local():
    user,remote_folder=request.args.get('path').split(':')
    resp=MakeResponse(render_template('admin/manage/upload_local.html',remote_folder=remote_folder,cur_user=user))
    return resp

@admin.route('/checkChunk', methods=['POST'])
def checkChunk():
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
        while 1:
            try:
                msg=_upload_session.next()['status']
                yield "data:" + msg + "\n\n"
            except Exception as e:
                exstr = traceback.format_exc()
                ErrorLogger().print_r(exstr)
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
        content=request.form.get('content').encode('utf-8')
        info=CreateFile(filename=filename,path=n_path,content=content,user=user)
        return jsonify(info)
    path=urllib.unquote(request.args.get('path'))
    if path.split(':')[-1]=='':
        path=path.split(':')[0]+':/'
    user,n_path=path.split(':')
    check_filepath=(path+'/'+filename).replace('//','/')
    check_data=mon_db.items.find_one({'path':check_filepath})
    if check_data:
        resp=MakeResponse(redirect(url_for('admin.edit',fileid=check_data['id'],user=check_data['user'])))
        return resp
    resp=MakeResponse(render_template('admin/setFile/setpass.html',path=path,filename=filename,cur_user=user))
    return resp


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
        InfoLogger().print_r('delete {}'.format(id))
        file=mon_db.items.find_one({'id':id})
        if file is not None and file != False:
            name=file['name']
            path=file['path'].replace(name,'')
            if len(path.split('/'))>2 and path.split('/')[-1]=='':
                path=path[:-1]
            key='has_item$#$#$#$#{}$#$#$#$#{}'.format(path,name)
            InfoLogger().print_r('delete key:{}'.format(key))
            redis_client.delete(key)
            kc='{}:content'.format(id)
            redis_client.delete(kc)
            status=DeleteRemoteFile(id,user)
            if status:
                infos['delete']+=1
            else:
                infos['fail']+=1
        else:
            infos['fail']+=1
    
    cmd="python -u {} UpdateFile {}".format(os.path.join(config_dir,'function.py'),'new')
    subprocess.Popen(cmd,shell=True)

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

@admin.route('/rename',methods=['POST'])
def Rename():
    fileid=request.form.get('fileid')
    user=request.form.get('user')
    new_name=request.form.get('new_name')
    if new_name=='' or new_name is None:
        return jsonify({'result':result})
    else:
        if new_name.startswith('/'):
            new_name=new_name[1:]
        if new_name.endswith('/'):
            new_name=new_name[:-1]
    result=ReName(fileid,new_name,user)
    return jsonify({'result':result})

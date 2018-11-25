#-*- coding=utf-8 -*-
from __future__ import print_function
import json
import requests
import collections
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
if sys.version_info[0]==3:
    import urllib.parse as urllib
else:
    import urllib
import os
import re
import time
import shutil
import base64
import humanize
import StringIO
import subprocess
from dateutil.parser import parse
from Queue import Queue
from threading import Thread
from redis import Redis
from config import *
from aria2 import PyAria2
from pymongo import MongoClient,ASCENDING,DESCENDING
######mongodb
client = MongoClient('localhost',27017)
db=client.three
items=db.items
down_db=db.down_db
rd=Redis(host='localhost',port=6379)

#######授权链接
LoginUrl=BaseAuthUrl+'/common/oauth2/v2.0/authorize?response_type=code\
&client_id={client_id}&redirect_uri={redirect_uri}&scope=offline_access%20files.readwrite.all'
OAuthUrl=BaseAuthUrl+'/common/oauth2/v2.0/token'
AuthData='client_id={client_id}&redirect_uri={redirect_uri}&client_secret={client_secret}&code={code}&grant_type=authorization_code'
ReFreshData='client_id={client_id}&redirect_uri={redirect_uri}&client_secret={client_secret}&refresh_token={refresh_token}&grant_type=refresh_token'

headers={'User-Agent':'ISV|PyOne|PyOne/2.0'}

def convert2unicode(string):
    return string.encode('utf-8')

def get_value(key,user='A'):
    allow_key=['client_secret','client_id']
    #print('get user {}\'s {}'.format(user,key))
    if key not in allow_key:
        return u'禁止获取'
    config_path=os.path.join(config_dir,'config.py')
    with open(config_path,'r') as f:
        text=f.read()
    kv=re.findall('"{}":{{[\w\W]*}}'.format(user),text)[0]
    value=re.findall('"{}":"(.*?)"'.format(key),kv)[0]
    return value

def GetName(id):
    key='name:{}'.format(id)
    if rd.exists(key):
        return rd.get(key)
    else:
        item=items.find_one({'id':id})
        rd.set(key,item['name'])
        return item['name']

def GetPath(id):
    key='path:{}'.format(id)
    if rd.exists(key):
        return rd.get(key)
    else:
        item=items.find_one({'id':id})
        rd.set(key,item['path'])
        return item['path']


################################################################################
###################################授权函数#####################################
################################################################################
def open_json(filepath):
    token=False
    with open(filepath,'r') as f:
        try:
            token=json.load(f)
        except:
            for i in range(1,10):
                try:
                    token=json.loads(f.read()[:-i])
                except:
                    token=False
                if token!=False:
                    return token
    return token

def ReFreshToken(refresh_token,user='A'):
    client_id=get_value('client_id',user)
    client_secret=get_value('client_secret',user)
    headers['Content-Type']='application/x-www-form-urlencoded'
    data=ReFreshData.format(client_id=client_id,redirect_uri=urllib.quote(redirect_uri),client_secret=client_secret,refresh_token=refresh_token)
    url=OAuthUrl
    r=requests.post(url,data=data,headers=headers)
    return json.loads(r.text)


def GetToken(Token_file='token.json',user='A'):
    Token_file='{}_{}'.format(user,Token_file)
    token_path=os.path.join(data_dir,Token_file)
    if os.path.exists(token_path):
        token=open_json(token_path)
        try:
            if time.time()>float(token.get('expires_on')):
                print('token timeout')
                refresh_token=token.get('refresh_token')
                token=ReFreshToken(refresh_token,user)
                if token.get('access_token'):
                    with open(token_path,'w') as f:
                        json.dump(token,f,ensure_ascii=False)
                else:
                    print(token)
        except:
            with open(os.path.join(data_dir,'{}_Atoken.json'.format(user)),'r') as f:
                Atoken=json.load(f)
            refresh_token=Atoken.get('refresh_token')
            token=ReFreshToken(refresh_token,user)
            token['expires_on']=str(time.time()+3599)
            if token.get('access_token'):
                    with open(token_path,'w') as f:
                        json.dump(token,f,ensure_ascii=False)
        return token.get('access_token')
    else:
        return False



def GetAppUrl():
    return 'https://graph.microsoft.com/'

################################################################################
###############################onedrive操作函数#################################
################################################################################
def GetExt(name):
    try:
        return name.split('.')[-1]
    except:
        return 'file'

def date_to_char(date):
    return date.strftime('%Y/%m/%d')

def Dir(path=u'A:/'):
    app_url=GetAppUrl()
    user,n_path=path.split(':')
    print('update {}\'s file'.format(user))
    if n_path=='/':
        BaseUrl=app_url+u'v1.0/me/drive/root/children?expand=thumbnails'
        # items.remove()
        queue=Queue()
        # queue.put(dict(url=BaseUrl,grandid=grandid,parent=parent,trytime=1))
        g=GetItemThread(queue,user)
        g.GetItem(BaseUrl)
        queue=g.queue
        if queue.qsize()==0:
            return
        tasks=[]
        for i in range(min(5,queue.qsize())):
            t=GetItemThread(queue,user)
            t.start()
            tasks.append(t)
        for t in tasks:
            t.join()
        RemoveRepeatFile()
    else:
        grandid=0
        parent=''
        if n_path.endswith('/'):
            n_path=n_path[:-1]
        if not n_path.startswith('/'):
            n_path='/'+n_path
        n_path=urllib.quote(n_path.encode('utf-8'))
        BaseUrl=app_url+u'v1.0/me/drive/root:{}:/children?expand=thumbnails'.format(n_path)
        queue=Queue()
        # queue.put(dict(url=BaseUrl,grandid=grandid,parent=parent,trytime=1))
        g=GetItemThread(queue,user)
        g.GetItem(BaseUrl,grandid,parent,1)
        queue=g.queue
        if queue.qsize()==0:
            return
        tasks=[]
        for i in range(min(10,queue.qsize())):
            t=GetItemThread(queue,user)
            t.start()
            tasks.append(t)
        for t in tasks:
            t.join()
        RemoveRepeatFile()

def Dir_all(path=u'A:/'):
    app_url=GetAppUrl()
    user,n_path=path.split(':')
    print('update {}\'s {} file'.format(user,n_path))
    if n_path=='/':
        BaseUrl=app_url+u'v1.0/me/drive/root/children?expand=thumbnails'
        items.remove({'user':user})
        queue=Queue()
        g=GetItemThread(queue,user)
        g.GetItem(BaseUrl)
        queue=g.queue
        if queue.qsize()==0:
            return
        tasks=[]
        for i in range(min(5,queue.qsize())):
            t=GetItemThread(queue,user)
            t.start()
            tasks.append(t)
        for t in tasks:
            t.join()
        RemoveRepeatFile()
    else:
        grandid=0
        parent=''
        if n_path.endswith('/'):
            n_path=n_path[:-1]
        if not n_path.startswith('/'):
            n_path='/'+n_path
        if items.find_one({'grandid':0,'type':'folder','user':user}):
            parent_id=0
            for idx,p in enumerate(n_path[1:].split('/')):
                if parent_id==0:
                    parent_id=items.find_one({'name':p,'grandid':idx,'user':user})['id']
                else:
                    parent_id=items.find_one({'name':p,'grandid':idx,'parent':parent_id})['id']
                items.delete_many({'parent':parent_id})
            grandid=idx+1
            parent=parent_id
        n_path=urllib.quote(n_path.encode('utf-8'))
        BaseUrl=app_url+u'v1.0/me/drive/root:{}:/children?expand=thumbnails'.format(n_path)
        queue=Queue()
        g=GetItemThread(queue,user)
        g.GetItem(BaseUrl,grandid,parent,1)
        queue=g.queue
        if queue.qsize()==0:
            return
        tasks=[]
        for i in range(min(10,queue.qsize())):
            t=GetItemThread(queue,user)
            t.start()
            tasks.append(t)
        for t in tasks:
            t.join()
        RemoveRepeatFile()

class GetItemThread(Thread):
    def __init__(self,queue,user):
        super(GetItemThread,self).__init__()
        self.queue=queue
        self.user=user
        share_path=od_users.get(user).get('share_path')
        if share_path=='/':
            self.share_path=share_path
        else:
            sp=share_path
            if not sp.startswith('/'):
                sp='/'+share_path
            if sp.endswith('/') and sp!='/':
                sp=sp[:-1]
            self.share_path=sp

    def run(self):
        while True:
            time.sleep(0.5) #避免过快
            info=self.queue.get()
            url=info['url']
            grandid=info['grandid']
            parent=info['parent']
            trytime=info['trytime']
            self.GetItem(url,grandid,parent,trytime)
            if self.queue.empty():
                time.sleep(5) #再等5s
                print('waiting 5s if queue is not empty')
                if self.queue.empty():
                    break

    def GetItem(self,url,grandid=0,parent='',trytime=1):
        app_url=GetAppUrl()
        token=GetToken(user=self.user)
        print(u'getting files from url {}'.format(url))
        header={'Authorization': 'Bearer {}'.format(token)}
        try:
            r=requests.get(url,headers=header)
            data=json.loads(r.content)
            if data.get('error'):
                print('error:{}! waiting 180s'.format(data.get('error').get('message')))
                time.sleep(180)
                self.queue.put(dict(url=url,grandid=grandid,parent=parent,trytime=trytime))
                return
            values=data.get('value')
            if len(values)>0:
                for value in values:
                    item={}
                    if value.get('folder'):
                        folder=items.find_one({'id':value['id']})
                        if folder is not None:
                            if folder['size_order']==value['size']: #文件夹大小未变化，不更新
                                print(u'path:{},origin size:{},current size:{}--------no change'.format(value['name'],folder['size_order'],value['size']))
                            else:
                                items.delete_one({'id':value['id']})
                                item['type']='folder'
                                item['user']=self.user
                                item['order']=0
                                item['name']=convert2unicode(value['name'])
                                item['id']=convert2unicode(value['id'])
                                item['size']=humanize.naturalsize(value['size'], gnu=True)
                                item['size_order']=int(value['size'])
                                item['lastModtime']=date_to_char(parse(value['lastModifiedDateTime']))
                                item['grandid']=grandid
                                item['parent']=parent
                                grand_path=value.get('parentReference').get('path').replace('/drive/root:','')
                                if grand_path=='':
                                    path=convert2unicode(value['name'])
                                else:
                                    path=grand_path.replace(self.share_path,'',1)+'/'+convert2unicode(value['name'])
                                if path.startswith('/') and path!='/':
                                    path=path[1:]
                                if path=='':
                                    path=convert2unicode(value['name'])
                                path='{}:/{}'.format(self.user,path)
                                item['path']=path
                                subfodler=items.insert_one(item)
                                if value.get('folder').get('childCount')==0:
                                    continue
                                else:
                                    parent_path=value.get('parentReference').get('path').replace('/drive/root:','')
                                    path=urllib.quote(convert2unicode(parent_path+'/'+value['name']))
                                    url=app_url+'v1.0/me/drive/root:{}:/children?expand=thumbnails'.format(path)
                                    self.queue.put(dict(url=url,grandid=grandid+1,parent=item['id'],trytime=1))
                        else:
                            items.delete_one({'id':value['id']})
                            item['type']='folder'
                            item['user']=self.user
                            item['order']=0
                            item['name']=convert2unicode(value['name'])
                            item['id']=convert2unicode(value['id'])
                            item['size']=humanize.naturalsize(value['size'], gnu=True)
                            item['size_order']=int(value['size'])
                            item['lastModtime']=date_to_char(parse(value['lastModifiedDateTime']))
                            item['grandid']=grandid
                            item['parent']=parent
                            grand_path=value.get('parentReference').get('path').replace('/drive/root:','')
                            if grand_path=='':
                                path=convert2unicode(value['name'])
                            else:
                                path=grand_path.replace(self.share_path,'',1)+'/'+convert2unicode(value['name'])
                            if path.startswith('/') and path!='/':
                                path=path[1:]
                            if path=='':
                                path=convert2unicode(value['name'])
                            path='{}:/{}'.format(self.user,path)
                            item['path']=path
                            subfodler=items.insert_one(item)
                            if value.get('folder').get('childCount')==0:
                                continue
                            else:
                                parent_path=value.get('parentReference').get('path').replace('/drive/root:','')
                                path=urllib.quote(convert2unicode(parent_path+'/'+value['name']))
                                url=app_url+'v1.0/me/drive/root:{}:/children?expand=thumbnails'.format(path)
                                self.queue.put(dict(url=url,grandid=grandid+1,parent=item['id'],trytime=1))
                    else:
                        if items.find_one({'id':value['id']}) is not None: #文件存在
                            continue
                        else:
                            item['type']=GetExt(value['name'])
                            grand_path=value.get('parentReference').get('path').replace('/drive/root:','')
                            if grand_path=='':
                                path=convert2unicode(value['name'])
                            else:
                                path=grand_path.replace(self.share_path,'',1)+'/'+convert2unicode(value['name'])
                            if path.startswith('/') and path!='/':
                                path=path[1:]
                            if path=='':
                                path=convert2unicode(value['name'])
                            path='{}:/{}'.format(self.user,path)
                            item['path']=path
                            item['user']=self.user
                            item['name']=convert2unicode(value['name'])
                            item['id']=convert2unicode(value['id'])
                            item['size']=humanize.naturalsize(value['size'], gnu=True)
                            item['size_order']=int(value['size'])
                            item['lastModtime']=date_to_char(parse(value['lastModifiedDateTime']))
                            item['grandid']=grandid
                            item['parent']=parent
                            if GetExt(value['name']) in ['bmp','jpg','jpeg','png','gif']:
                                item['order']=3
                                key1='name:{}'.format(value['id'])
                                key2='path:{}'.format(value['id'])
                                rd.set(key1,value['name'])
                                rd.set(key2,path)
                            elif value['name']=='.password':
                                item['order']=1
                            else:
                                item['order']=2
                            items.insert_one(item)
            if data.get('@odata.nextLink'):
                self.queue.put(dict(url=data.get('@odata.nextLink'),grandid=grandid,parent=parent,trytime=1))
        except Exception as e:
            trytime+=1
            print(u'error to opreate GetItem("{}","{}","{}"),try times :{}, reason: {}'.format(url,grandid,parent,trytime,e))
            if trytime<=3:
                self.queue.put(dict(url=url,grandid=grandid,parent=parent,trytime=trytime))


    def GetItemByPath(self,path):
        app_url=GetAppUrl()
        token=GetToken(user=self.user)
        path=urllib.quote(convert2unicode(path))
        if path=='' or path=='/':
            url=app_url+u'v1.0/me/drive/root/'
        else:
            url=app_url+u'v1.0/me/drive/root:{}:/'.format(path)
        header={'Authorization': 'Bearer {}'.format(token)}
        r=requests.get(url,headers=header)
        data=json.loads(r.content)
        return data

    def GetItemByUrl(self,url):
        app_url=GetAppUrl()
        token=GetToken(user=self.user)
        header={'Authorization': 'Bearer {}'.format(token)}
        r=requests.get(url,headers=header)
        data=json.loads(r.content)
        return data

def GetRootid(user='A'):
    key='{}:rootid'.format(user)
    if rd.exists(key):
        return rd.get(key)
    else:
        app_url=GetAppUrl()
        token=GetToken(user=user)
        url=app_url+u'v1.0/me/drive/root/'
        header={'Authorization': 'Bearer {}'.format(token)}
        r=requests.get(url,headers=header)
        data=json.loads(r.content)
        rd.set(key,data['id'],3600)
        return data['id']

def UpdateFile(renew='all'):
    if renew=='all':
        items.remove()
        rd.flushdb()
        for user,item in od_users.items():
            if item.get('client_id')!='':
                share_path='{}:{}'.format(user,item['share_path'])
                Dir_all(share_path)
    else:
        for user,item in od_users.items():
            if item.get('client_id')!='':
                share_path='{}:{}'.format(user,item['share_path'])
                Dir(share_path)
    print('update file success!')


def FileExists(filename,user='A'):
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    search_url=app_url+"v1.0/me/drive/root/search(q='{}')".format(convert2unicode(filename))
    r=requests.get(search_url,headers=headers)
    jsondata=json.loads(r.text)
    if len(jsondata['value'])==0:
        return False
    else:
        return True

def FileInfo(fileid,user='A'):
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    search_url=app_url+"v1.0/me/drive/items/{}".format(fileid)
    r=requests.get(search_url,headers=headers)
    jsondata=json.loads(r.text)
    return jsondata


################################################上传文件
def list_all_files(rootdir):
    import os
    _files = []
    if len(re.findall('[:#\|\?]+',rootdir))>0:
        newf=re.sub('[:#\|\?]+','',rootdir)
        shutil.move(rootdir,newf)
        rootdir=newf
    if rootdir.endswith(' '):
        shutil.move(rootdir,rootdir.rstrip())
        rootdir=rootdir.rstrip()
    if len(re.findall('/ ',rootdir))>0:
        newf=re.sub('/ ','/',rootdir)
        shutil.move(rootdir,newf)
        rootdir=newf
    flist = os.listdir(rootdir) #列出文件夹下所有的目录与文件
    for f in flist:
        path = os.path.join(rootdir,f)
        if os.path.isdir(path):
            _files.extend(list_all_files(path))
        if os.path.isfile(path):
            _files.append(path)
    return _files

def _filesize(path):
    size=os.path.getsize(path)
    # print('{}\'s size {}'.format(path,size))
    return size

def _file_content(path,offset,length):
    size=_filesize(path)
    offset,length=map(int,(offset,length))
    if offset>size:
        print('offset must smaller than file size')
        return False
    length=length if offset+length<size else size-offset
    endpos=offset+length-1 if offset+length<size else size-1
    # print("read file {} from {} to {}".format(path,offset,endpos))
    with open(path,'rb') as f:
        f.seek(offset)
        content=f.read(length)
    return content



def _upload(filepath,remote_path,user='A'): #remote_path like 'share/share.mp4'
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token)}
    url=app_url+'v1.0/me/drive/root:{}:/content'.format(urllib.quote(convert2unicode(remote_path)))
    r=requests.put(url,headers=headers,data=open(filepath,'rb'))
    data=json.loads(r.content)
    trytime=1
    while True:
        try:
            if data.get('error'):
                print(data.get('error').get('message'))
                yield {'status':'upload fail!'}
                break
            elif r.status_code==201 or r.status_code==200:
                print('upload {} success!'.format(filepath))
                AddResource(data,user)
                yield {'status':'upload success!'}
                break
            else:
                print(data)
                yield {'status':'upload fail!'}
                break
        except Exception as e:
            trytime+=1
            print('error to opreate _upload("{}","{}"), try times {},error:{}'.format(filepath,remote_path,trytime,e))
            yield {'status':'upload fail! retry!'}
        if trytime>3:
            yield {'status':'upload fail! touch max retry time(3)'}
            break

def _upload_part(uploadUrl, filepath, offset, length,trytime=1):
    size=_filesize(filepath)
    offset,length=map(int,(offset,length))
    if offset>size:
        print('offset must smaller than file size')
        return {'status':'fail','msg':'params mistake','code':1}
    length=length if offset+length<size else size-offset
    endpos=offset+length-1 if offset+length<size else size-1
    print('upload file {} {}%'.format(filepath,round(float(endpos)/size*100,1)))
    filebin=_file_content(filepath,offset,length)
    headers={}
    # headers['Authorization']='bearer {}'.format(token)
    headers['Content-Length']=str(length)
    headers['Content-Range']='bytes {}-{}/{}'.format(offset,endpos,size)
    try:
        r=requests.put(uploadUrl,headers=headers,data=filebin)
        data=json.loads(r.content)
        if r.status_code==201 or r.status_code==200:
            print(u'{} upload success!'.format(filepath))
            return {'status':'success','msg':'all upload success','code':0,'info':data}
        elif r.status_code==202:
            offset=data.get('nextExpectedRanges')[0].split('-')[0]
            return {'status':'success','msg':'partition upload success','code':1,'offset':offset}
        else:
            trytime+=1
            if trytime<=3:
                return {'status':'fail'
                        ,'msg':'please retry'
                        ,'sys_msg':data.get('error').get('message')
                        ,'code':2,'trytime':trytime}
            else:
                return {'status':'fail'
                        ,'msg':'retry times limit'
                        ,'sys_msg':data.get('error').get('message')
                        ,'code':3}
    except Exception as e:
        print('error to opreate _upload_part("{}","{}","{}","{}"), try times {},reason:{}'.format(uploadUrl, filepath, offset, length,trytime,e))
        trytime+=1
        if trytime<=3:
            return {'status':'fail','msg':'please retry','code':2,'trytime':trytime,'sys_msg':''}
        else:
            return {'status':'fail','msg':'retry times limit','code':3,'sys_msg':''}


def _GetAllFile(parent_id="",parent_path="",filelist=[]):
    for f in db.items.find({'parent':parent_id}):
        if f['type']=='folder':
            _GetAllFile(f['id'],'/'.join([parent_path,f['name']]),filelist)
        else:
            fp='/'.join([parent_path,f['name']])
            if fp.startswith('/'):
                fp=base64.b64encode(fp[1:].encode('utf-8'))
            else:
                fp=base64.b64encode(fp.encode('utf-8'))
            filelist.append(fp)
    return filelist


def AddResource(data,user='A'):
    #检查父文件夹是否在数据库，如果不在则获取添加
    grand_path=data.get('parentReference').get('path').replace('/drive/root:','')
    share_path=od_users.get(user).get('share_path')
    if grand_path=='':
        parent_id=''
        grandid=0
    else:
        g=GetItemThread(Queue(),user)
        parent_id=data.get('parentReference').get('id')
        grandid=len(data.get('parentReference').get('path').replace('/drive/root:','').split('/'))-1
        grand_path=grand_path[1:]
        parent_path='/'
        pid=''
        for idx,p in enumerate(grand_path.split('/')):
            parent=items.find_one({'name':p,'grandid':idx,'parent':pid})
            if parent is not None:
                pid=parent['id']
                parent_path='/'.join([parent_path,parent['name']])
            else:
                parent_path='/'.join([parent_path,p])
                fdata=g.GetItemByPath(parent_path)
                path=user+':/'+parent_path.replace('///','/')
                path=path.replace('///','/').replace('//','/')
                item={}
                item['type']='folder'
                item['user']=user
                item['order']=0
                item['name']=fdata.get('name')
                item['id']=fdata.get('id')
                item['size']=humanize.naturalsize(fdata.get('size'), gnu=True)
                item['size_order']=fdata.get('size')
                item['lastModtime']=date_to_char(parse(fdata['lastModifiedDateTime']))
                item['grandid']=idx
                item['parent']=pid
                item['path']=path
                items.insert_one(item)
                pid=fdata.get('id')
    #插入数据
    item={}
    item['type']='file'
    item['name']=data.get('name')
    item['user']=user
    item['id']=data.get('id')
    item['size']=humanize.naturalsize(data.get('size'), gnu=True)
    item['size_order']=data.get('size')
    item['lastModtime']=date_to_char(parse(data.get('lastModifiedDateTime')))
    item['grandid']=grandid
    item['parent']=parent_id
    if grand_path=='':
        path=convert2unicode(data['name'])
    else:
        if share_path!='/':
            path=user+':/'+grand_path.replace(share_path,'',1)+'/'+convert2unicode(data['name'])
        else:
            path=user+':/'+grand_path+'/'+convert2unicode(data['name'])
    print('new file path:{}'.format(path))
    item['path']=path
    if GetExt(data['name']) in ['bmp','jpg','jpeg','png','gif']:
        item['order']=3
        key1='name:{}'.format(data['id'])
        key2='path:{}'.format(data['id'])
        rd.set(key1,data['name'])
        rd.set(key2,path)
    elif data['name']=='.password':
        item['order']=1
    else:
        item['order']=2
    items.insert_one(item)


def CreateUploadSession(path,user='A'):
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    url=app_url+u'v1.0/me/drive/root:{}:/createUploadSession'.format(urllib.quote(convert2unicode(path)))
    data={
          "item": {
            "@microsoft.graph.conflictBehavior": "rename",
          }
        }
    try:
        r=requests.post(url,headers=headers,data=json.dumps(data))
        retdata=json.loads(r.content)
        if r.status_code==409:
            print('file exists')
            return False
        else:
            return retdata
    except Exception as e:
        print('error to opreate CreateUploadSession("{}"),reason {}'.format(path,e))
        return False

def UploadSession(uploadUrl, filepath,user):
    length=327680*10
    offset=0
    trytime=1
    filesize=_filesize(filepath)
    while True:
        result=_upload_part(uploadUrl, filepath, offset, length,trytime=trytime)
        code=result['code']
        #上传完成
        if code==0:
            AddResource(result['info'],user)
            yield {'status':'upload success!','uploadUrl':uploadUrl}
            break
        #分片上传成功
        elif code==1:
            trytime=1
            offset=result['offset']
            per=round((float(offset)/filesize)*100,1)
            yield {'status':'partition upload success! {}%'.format(per),'uploadUrl':uploadUrl}
        #错误，重试
        elif code==2:
            if result['sys_msg']=='The request has been throttled':
                print(result['sys_msg']+' ; wait for 1800s')
                yield {'status':'The request has been throttled! wait for 1800s','uploadUrl':uploadUrl}
                time.sleep(1800)
            offset=offset
            trytime=result['trytime']
            yield {'status':'partition upload fail! retry!','uploadUrl':uploadUrl}
        #重试超过3次，放弃
        elif code==3:
            yield {'status':'partition upload fail! touch max retry times!','uploadUrl':uploadUrl}
            break

def Upload_for_server(filepath,remote_path=None,user='A'):
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    if remote_path is None:
        remote_path=os.path.basename(filepath)
    if remote_path.endswith('/'):
        remote_path=os.path.join(remote_path,os.path.basename(filepath))
    if not remote_path.startswith('/'):
        remote_path='/'+remote_path
    filepath=convert2unicode(filepath)
    remote_path=convert2unicode(remote_path)
    print('local file path:{}, remote file path:{}'.format(filepath,remote_path))
    if _filesize(filepath)<1024*1024*3.25:
        for msg in _upload(filepath,remote_path,user):
            yield msg
    else:
        session_data=CreateUploadSession(remote_path,user)
        if session_data==False:
            yield {'status':'file exists!'}
        else:
            if session_data.get('uploadUrl'):
                uploadUrl=session_data.get('uploadUrl')
                for msg in UploadSession(uploadUrl,filepath,user):
                    yield msg
            else:
                print('user:{} create upload session fail! {},{}'.format(user,remote_path,session_data.get('error').get('message')))
                yield {'status':'user:{};create upload session fail!{}'.format(user,session_data.get('error').get('message'))}

def ContinueUpload(filepath,uploadUrl,user):
    headers={'Content-Type':'application/json'}
    r=requests.get(uploadUrl,headers=headers)
    data=json.loads(r.text)
    offset=data.get('nextExpectedRanges')[0].split('-')[0]
    expires_on=time.mktime(parse(data.get('expirationDateTime')).timetuple())
    if time.time()>expires_on:
        yield 'alright expired!'
    else:
        length=327680*10
        trytime=1
        filesize=_filesize(filepath)
        while True:
            result=_upload_part(uploadUrl, filepath, offset, length,trytime=trytime)
            code=result['code']
            #上传完成
            if code==0:
                AddResource(result['info'],user)
                yield {'status':'upload success!'}
                break
            #分片上传成功
            elif code==1:
                trytime=1
                offset=result['offset']
                per=round((float(offset)/filesize)*100,1)
                yield {'status':'partition upload success! {}%'.format(per)}
            #错误，重试
            elif code==2:
                if result['sys_msg']=='The request has been throttled':
                    print(result['sys_msg']+' ; wait for 1800s')
                    yield {'status':'The request has been throttled! wait for 1800s'}
                    time.sleep(1800)
                offset=offset
                trytime=result['trytime']
                yield {'status':'partition upload fail! retry!'}
            #重试超过3次，放弃
            elif code==3:
                yield {'status':'partition upload fail! touch max retry times!'}
                break



def Upload(filepath,remote_path=None,user='A'):
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    if remote_path is None:
        remote_path=os.path.basename(filepath)
    if remote_path.endswith('/'):
        remote_path=os.path.join(remote_path,os.path.basename(filepath))
    if not remote_path.startswith('/'):
        remote_path='/'+remote_path
    if _filesize(filepath)<1024*1024*3.25:
        for msg in _upload(filepath,remote_path,user):
            1
    else:
        session_data=CreateUploadSession(remote_path,user)
        if session_data==False:
            return {'status':'file exists!'}
        else:
            if session_data.get('uploadUrl'):
                uploadUrl=session_data.get('uploadUrl')
                for msg in UploadSession(uploadUrl,filepath,user):
                    1
            else:
                print(session_data.get('error').get('msg'))
                print('create upload session fail! {}'.format(remote_path))
                return {'status':'create upload session fail!'}


class MultiUpload(Thread):
    def __init__(self,waiting_queue,user):
        super(MultiUpload,self).__init__()
        self.queue=waiting_queue
        self.user=user

    def run(self):
        while not self.queue.empty():
            localpath,remote_dir=self.queue.get()
            Upload(localpath,remote_dir,self.user)


def UploadDir(local_dir,remote_dir,user,threads=5):
    print(u'geting file from dir {}'.format(local_dir))
    localfiles=list_all_files(local_dir)
    print(u'get {} files from dir {}'.format(len(localfiles),local_dir))
    print(u'check filename')
    for f in localfiles:
        dir_,fname=os.path.dirname(f),os.path.basename(f)
        if len(re.findall('[:/#\|]+',fname))>0:
            newf=os.path.join(dir_,re.sub('[:/#\|]+','',fname))
            shutil.move(f,newf)
    localfiles=list_all_files(local_dir)
    check_file_list=[]
    if local_dir.endswith('/'):
        local_dir=local_dir[:-1]
    for file in localfiles:
        dir_,fname=os.path.dirname(file),os.path.basename(file)
        remote_path=remote_dir+'/'+dir_.replace(local_dir,'')+'/'+fname
        remote_path=remote_path.replace('//','/')
        check_file_list.append((remote_path,file))
    print(u'check repeat file')
    if remote_dir=='/':
        cloud_files=_GetAllFile()
    else:
        if remote_dir.startswith('/'):
            remote_dir=remote_dir[1:]
        if items.find_one({'grandid':0,'type':'folder','name':remote_dir.split('/')[0]}):
            parent_id=0
            parent_path=''
            for idx,p in enumerate(remote_dir.split('/')):
                if parent_id==0:
                    parent=items.find_one({'name':p,'grandid':idx})
                    parent_id=parent['id']
                    parent_path='/'.join([parent_path,parent['name']])
                else:
                    parent=items.find_one({'name':p,'grandid':idx,'parent':parent_id})
                    parent_id=parent['id']
                    parent_path='/'.join([parent_path,parent['name']])
            grandid=idx+1
            cloud_files=_GetAllFile(parent_id,parent_path)
    try:
        cloud_files=dict([(i,i) for i in cloud_files])
    except:
        cloud_files={}
    queue=Queue()
    tasks=[]
    for remote_path,file in check_file_list:
        if not cloud_files.get(base64.b64encode(remote_path)):
            queue.put((file,remote_path))
    print("check_file_list {},cloud_files {},queue {}".format(len(check_file_list),len(cloud_files),queue.qsize()))
    print("start upload files 5s later")
    time.sleep(5)
    for i in range(min(threads,queue.qsize())):
        t=MultiUpload(queue,user)
        t.start()
        tasks.append(t)
    for t in tasks:
        t.join()
    #删除错误数据
    RemoveRepeatFile()



########################删除文件
def DeleteLocalFile(fileid):
    items.remove({'id':fileid})

def DeleteRemoteFile(fileid,user='A'):
    app_url=GetAppUrl()
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token)}
    url=app_url+'v1.0/me/drive/items/'+fileid
    r=requests.delete(url,headers=headers)
    if r.status_code==204:
        DeleteLocalFile(fileid)
        return True
    else:
        DeleteLocalFile(fileid)
        return False

########################
def CreateFolder(folder_name,grand_path,user='A'):
    app_url=GetAppUrl()
    token=GetToken(user=user)
    if grand_path=='' or grand_path is None or grand_path=='/':
        url=app_url+'v1.0/me/drive/root/children'
        parent_id=''
        grandid=0
    else:
        path='{}:/{}'.format(user,grand_path)
        parent=items.find_one({'path':path})
        parent_id=parent['id']
        grandid=parent['grandid']+1
        url=app_url+'v1.0/me/drive/items/{}/children'.format(parent['id'])
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    payload={
      "name": folder_name,
      "folder": {},
      "@microsoft.graph.conflictBehavior": "rename"
    }
    r=requests.post(url,headers=headers,data=json.dumps(payload))
    data=json.loads(r.content)
    if data.get('id'):
        #插入数据
        share_path=od_users.get(user).get('share_path')
        item={}
        item['type']='folder'
        item['user']=user
        item['name']=data.get('name')
        item['id']=data.get('id')
        item['size']=humanize.naturalsize(data.get('size'), gnu=True)
        item['size_order']=data.get('size')
        item['lastModtime']=date_to_char(parse(data.get('lastModifiedDateTime')))
        item['grandid']=grandid
        item['parent']=parent_id
        if grand_path=='' or grand_path is None or grand_path=='/':
            path=convert2unicode(data['name'])
        else:
            path=grand_path.replace(share_path,'',1)+'/'+convert2unicode(data['name'])
        if not path.startswith('/'):
            path='/'+path
        path='{}:{}'.format(user,path)
        item['path']=path
        item['order']=0
        items.insert_one(item)
        return True
    else:
        print(data.get('error').get('msg'))
        return False

def MoveFile(fileid,new_folder_path,user='A'):
    app_url=GetAppUrl()
    token=GetToken(user=user)
    #GetRootid
    if new_folder_path=='' or new_folder_path is None or new_folder_path=='/':
        folder_id=GetRootid(user)
        parent=''
        grandid=0
        path=GetName(fileid)
    else:
        path='{}:/{}'.format(user,new_folder_path)
        parent_item=items.find_one({'path':path})
        folder_id=parent_item['id']
        parent=parent_item['id']
        grandid=parent_item['grandid']+1
        path=parent_item['path']+'/'+GetName(fileid)
    url=app_url+'v1.0/me/drive/items/{}'.format(fileid)
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    payload={
      "parentReference": {
        "id": folder_id
      },
      "name": GetName(fileid)
    }
    r=requests.patch(url,headers=headers,data=json.dumps(payload))
    data=json.loads(r.content)
    if data.get('id'):
        new_value={'parent':parent,'grandid':grandid,'path':path}
        items.find_one_and_update({'id':fileid},{'$set':new_value})
        file=items.find_one({'id':fileid})
        filename=file['name']
        if file['parent']=='':
            path='/'
        else:
            path=items.find_one({'id':file['parent']})['path']
        key='has_item$#$#$#$#{}$#$#$#$#{}'.format(path,filename)
        rd.delete(key)
        return True
    else:
        print(data.get('error').get('msg'))
        return False

def CheckTimeOut(fileid):
    app_url=GetAppUrl()
    token=GetToken()
    headers={'Authorization':'bearer {}'.format(token),'Content-Type':'application/json'}
    url=app_url+'v1.0/me/drive/items/'+fileid
    r=requests.get(url,headers=headers)
    data=json.loads(r.content)
    if data.get('@microsoft.graph.downloadUrl'):
        downloadUrl=data.get('@microsoft.graph.downloadUrl')
        start_time=time.time()
        for i in range(10000):
            r=requests.head(downloadUrl)
            print('{}\'s gone, status:{}'.format(time.time()-start_time,r.status_code))
            if r.status_code==404:
                break

def RemoveRepeatFile():
    """
    db.items.aggregate([
        {
            $group:{_id:{id:'$id'},count:{$sum:1},dups:{$addToSet:'$_id'}}
        },
        {
            $match:{count:{$gt:1}}
        }

        ]).forEach(function(it){

             it.dups.shift();
            db.items.remove({_id: {$in: it.dups}});

        });
    """
    deleteData=items.aggregate([
    {'$group': {
        '_id': { 'id': "$id"},
        'uniqueIds': { '$addToSet': "$_id" },
        'count': { '$sum': 1 }
      }},
      { '$match': {
        'count': { '$gt': 1 }
      }}
    ]);
    first=True
    try:
        for d in deleteData:
            first=True
            for did in d['uniqueIds']:
                if not first:
                    items.delete_one({'_id':did});
                first=False
    except Exception as e:
        print(e)
        return

def get_aria2():
    try:
        p=PyAria2()
        return p,True
    except Exception as e:
        return e,False



def download_and_upload(url,remote_dir,user,gid=None):
    p,status=get_aria2()
    down_path=os.path.join(config_dir,'upload')
    url=url.lower()
    #重新下载
    if gid is not None:
        task=down_db.find_one({'gid':gid})
        if task is None:
            return False
        if task['up_status']!='100.0%':
            new_value={}
            new_value['up_status']=u'待机'
            new_value['status']=1
            down_db.update_many({'gid':gid},{'$set':new_value})
    else:
        cur_order=down_db.count()
        option={"dir":down_path,"split":"16","max-connection-per-server":"8","seed-ratio":"0.1","header":["User-Agent:Transmission/2.77"]}
        item={}
        gid=json.loads(p.addUri(url,option))[0]["result"]
        item['gid']=gid
        a=json.loads(p.tellStatus(gid))[0]["result"]
        if 'magnet:?xt=' in url:
            name=re.findall('magnet:\?xt=urn:btih:(.{,40})',url)[0].lower()+'.torrent'
            localpath=os.path.join(down_path,name)
        else:
            name=a['files'][0]['path'].replace(down_path+'/','').replace(down_path,'').replace(down_path[:-1],'')
            localpath=a['files'][0]['path']
        item['name']=name
        item['idx']=0
        item['localpath']=localpath
        item['downloadUrl']=url
        item['selected']='true'
        item['selectable']='false'
        item['user']=user
        item['remote_dir']=remote_dir
        item['uploadUrl']=''
        item['size']=humanize.naturalsize(a['totalLength'], gnu=True)
        item['down_status']=u'{}%'.format(round(float(a['completedLength'])/(float(a['totalLength'])+0.1)*100,0))
        item['up_status']=u'待机'
        item['status']=1
        down_db.insert_one(item)
    while True:
        a=json.loads(p.tellStatus(gid))[0]["result"]
        if a.get('followedBy'):
            old_status={}
            old_status['status']=0
            old_status['up_status']=u'磁力文件，无需上传'
            down_db.find_one_and_update({'gid':gid},{'$set':old_status})
            magnet=re.findall('magnet:\?xt=urn:btih:(.{,40})',down_db.find_one({'gid':gid})['downloadUrl'])[0].lower()+'.torrent'
            old_path=os.path.join(down_path,magnet)
            try:
                os.remove(old_path)
            except:
                print("删除种子文件失败")
            gid=a.get('followedBy')[0]
            aa=json.loads(p.tellStatus(gid))[0]["result"]
            for idx,file in enumerate(aa['files']):
                new_item={}
                new_item['gid']=gid
                new_item['idx']=idx
                new_item['name']=file['path'].replace(down_path+'/','').replace(down_path,'').replace(down_path[:-1],'')
                new_item['localpath']=file['path']
                new_item['downloadUrl']=aa['infoHash']
                new_item['selected']='true'
                new_item['selectable']='true'
                new_item['user']=user
                new_item['remote_dir']=remote_dir
                new_item['uploadUrl']=''
                new_item['size']=humanize.naturalsize(file['length'], gnu=True)
                new_item['down_status']=u'{}%'.format(round(float(file['completedLength'])/(float(file['length'])+0.1)*100,0))
                new_item['up_status']=u'待机'
                new_item['status']=1
                down_db.insert_one(new_item)
            a=json.loads(p.tellStatus(gid))[0]["result"]
        total=len(a['files'])
        complete=0
        for idx,file in enumerate(a['files']):
            t=down_db.find_one({'gid':gid,'idx':idx})
            if t['down_status']=='100.0%':
                if t['up_status']=='待机':
                    new_value['up_status']=u'准备上传'
                    down_db.find_one_and_update({'gid':gid,'idx':idx},{'$set':new_value})
                    upload_status(gid,idx,remote_dir,user)
                elif t['up_status']=='上传成功！':
                    complete+=1
                else:
                    continue
            if t['selected']=='false':
                complete+=1
                continue
            name=file['path'].replace(down_path+'/','').replace(down_path,'').replace(down_path[:-1],'')
            new_value={'down_status':u'{}%'.format(round(float(file['completedLength'])/(float(file['length'])+0.1)*100,0))}
            new_value['name']=name
            new_value['size']=humanize.naturalsize(file['length'], gnu=True)
            new_value['localpath']=file['path']
            if a['status']=='complete' or (file['completedLength']==file['length'] and int(file['length'])!=0):
                new_value['up_status']=u'准备上传'
                down_db.find_one_and_update({'gid':gid,'idx':idx},{'$set':new_value})
                upload_status(gid,idx,remote_dir,user)
                complete+=1
            elif a['status']=='active' or a['status']=='waiting':
                time.sleep(1)
                down_db.find_one_and_update({'gid':gid,'idx':idx},{'$set':new_value})
            elif a['status']=='paused':
                new_value['down_status']=u'暂停下载'
                down_db.find_one_and_update({'gid':gid,'idx':idx},{'$set':new_value})
            else:
                print('下载出错')
                new_value['down_status']=u'下载出错'
                new_value['status']=-1
                down_db.find_one_and_update({'gid':gid,'idx':idx},{'$set':new_value})
                complete+=1
        time.sleep(2)
        if complete==total:
            print('{} complete'.format(gid))
            break

def upload_status(gid,idx,remote_dir,user):
    item=down_db.find_one({'gid':gid,'idx':idx})
    localpath=item['localpath']
    if not remote_dir.endswith('/'):
        remote_dir=remote_dir+'/'
    remote_path=os.path.join(remote_dir,item['name'])
    if not os.path.exists(localpath):
        new_value={}
        new_value['up_status']=u'本地文件不存在。检查：{}'.format(localpath)
        new_value['status']=-1
        down_db.find_one_and_update({'_id':item['_id']},{'$set':new_value})
        return
    _upload_session=Upload_for_server(localpath,remote_path,user)
    while True:
        try:
            new_value={}
            data=next(_upload_session)
            msg=data['status']
            """
            partition upload success
            The request has been throttled!
            partition upload fail! retry
            partition upload fail!
            file exists
            create upload session fail
            """
            if 'partition upload success' in msg:
                new_value['up_status']=msg
                new_value['uploadUrl']=data.get('uploadUrl')
                new_value['status']=1
            elif 'The request has been throttled' in msg:
                new_value['up_status']='api受限！智能等待30分钟'
                new_value['status']=0
            elif 'partition upload fail! retry' in msg:
                new_value['up_status']='上传失败，等待重试'
                new_value['status']=1
            elif 'partition upload fail' in msg:
                new_value['up_status']='上传失败，已经超过重试次数'
                new_value['status']=-1
                down_db.find_one_and_update({'_id':item['_id']},{'$set':new_value})
                break
            elif 'file exists' in msg:
                new_value['up_status']='远程文件已存在'
                new_value['status']=-1
                down_db.find_one_and_update({'_id':item['_id']},{'$set':new_value})
                break
            elif 'create upload session fail' in msg:
                new_value['up_status']='创建实例失败！'
                new_value['status']=-1
                down_db.find_one_and_update({'_id':item['_id']},{'$set':new_value})
                break
            else:
                new_value['up_status']='上传成功！'
                new_value['status']=0
                down_db.find_one_and_update({'_id':item['_id']},{'$set':new_value})
                os.remove(localpath)
                break
            down_db.find_one_and_update({'_id':item['_id']},{'$set':new_value})
        except Exception as e:
            print(e)
            break


def get_tasks(status):
    tasks=down_db.find({'status':status})
    result=[]
    for t in tasks:
        info={}
        info['gid']=t['gid']
        info['idx']=t['idx']
        info['name']=t['name']
        info['downloadUrl']=t['downloadUrl']
        info['size']=t['size']
        info['down_status']=t['down_status']
        info['up_status']=t['up_status']
        info['selectable']=t['selectable']
        info['selected']=t['selected']
        info['status']=t['status']
        result.append(info)
    return result

def Aria2Method(action,**kwargs):
    p,status=get_aria2()
    if not status:
        return {'status':False,'msg':p}
    if action in ['pause','unpause']:
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            p.forcePause(gid)
    elif action in ['pauseAll','unpauseAll']:
        eval('p.{}()'.format(action))
    elif action in ['remove']:
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            p.forceRemove(gid)
    elif action in ['removeAll']:
        for gid in kwargs['gids']:
            p.forceRemove(gid)
    elif action=='restart':
        for gid in kwargs['gids']:
            p.unpause(gid)
    elif action=='selected':
        retdata={}
        selected_dict={}
        status_dict={}
        #选择下载的gid&idx放进字典
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            idx=int(idx)
            # p.pause(gid)
            r=json.loads(p.tellStatus(gid))[0]['result']['status']
            status_dict[gid]=r
            if r=='active':
                p.forcePause(gid)
            selected_dict.setdefault(gid,[]).append(idx+1)
        #之前本就选择下载的gid&idx放进字典
        for gid in selected_dict.keys():
            tasks=down_db.find({'gid':gid,'selected':'true'})
            for t in tasks:
                selected_dict[gid].append(t['idx']+1)
        #重新处理可下载文件
        result=[]
        for gid,idxs in selected_dict.items():
            idxs=[str(i) for i in idxs]
            info={'gid':gid}
            option={"select-file":','.join(idxs)}
            r=p.changeOption(gid,option)
            if status_dict[gid]=='active':
                p.unpause(gid)
            res=json.loads(r)[0]['result']
            info['msg']=res
            result.append(info)
            for idx in idxs:
                new_value={'selected':'true','down_status':'选择下载','status':1}
                down_db.find_one_and_update({'gid':gid,'idx':int(idx)-1},{'$set':new_value})
        retdata['result']=result
        return retdata
    elif action=='unselected':
        retdata={}
        selected_dict={}
        status_dict={}
        #先创建围表
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            nums=down_db.find({'gid':gid}).count()
            if nums<=1:
                result=[{'gid':gid,'msg':'当前任务只有一个文件，无法选择'}]
                retdata['result']=result
                return retdata
            idx=int(idx)
            # p.pause(gid)
            r=json.loads(p.tellStatus(gid))[0]['result']['status']
            status_dict[gid]=r
            if r=='active':
                p.forcePause(gid)
            new_value={'selected':'false','down_status':'选择不下载','status':2}
            down_db.find_one_and_update({'gid':gid,'idx':idx},{'$set':new_value})
            selected_dict.setdefault(gid,[])
        #之前本就选择下载的gid&idx放进字典
        for gid in selected_dict.keys():
            tasks=down_db.find({'gid':gid,'selected':'true'})
            for t in tasks:
                selected_dict[gid].append(int(t['idx']+1))
        #选择不下载的gid&idx从字典移除
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            idx=int(idx)
            # selected_dict[gid].pop(selected_dict[gid].index(idx+1))
        #重新处理可下载文件
        result=[]
        for gid,idxs in selected_dict.items():
            idxs=[str(i) for i in idxs]
            info={'gid':gid}
            option={"select-file":','.join(idxs)}
            r=p.changeOption(gid,option)
            if status_dict[gid]=='active':
                p.unpause(gid)
            res=json.loads(r)[0]['result']
            info['msg']=res
            result.append(info)
        retdata['result']=result
        return retdata




def DBMethod(action,**kwargs):
    retdata={}
    if action in ['pause','unpause','pauseAll','unpauseAll']:
        result=[]
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            info={'gid':gid,'idx':int(idx)}
            task=down_db.find_one({'gid':gid,'idx':int(idx)})
            if task['down_status']=='100.0%':
                info['msg']='文件下载完成！无法更改上传状态'
            elif task['down_status']=='下载出错':
                info['msg']='失败任务只能重启'
            else:
                new_value={}
                if action in ['pauseAll','pause']:
                    new_value['down_status']='暂停下载'
                else:
                    new_value['down_status']='开始下载'
                down_db.update_many({'gid':gid},{'$set':new_value})
                info['msg']='更改状态成功'
            result.append(info)
    elif action in ['remove']:
        result=[]
        for gid in kwargs['gids']:
            gid,idx=gid.split('#')
            info={'gid':gid,'idx':int(idx)}
            task=down_db.find_one({'gid':gid,'idx':int(idx)})
            if task['down_status']=='100.0%' and 'partition upload success' in task['up_status']:
                info['msg']='正在上传的任务，无法更改状态'
            else:
                down_db.remove(info)
                info['msg']='删除任务成功'
            try:
                os.remove(task['localpath'])
            except:
                print('未能成功删除本地文件')
                info['msg']='删除任务成功。但是未能成功删除本地文件'
            result.append(info)
    elif action in ['removeAll']:
        result=[]
        for gid in kwargs['gids']:
            info={'gid':gid}
            task=down_db.find_one({'gid':gid})
            if task['down_status']=='100.0%' and 'partition upload success' in task['up_status']:
                info['msg']='正在上传的任务，无法更改状态'
            else:
                down_db.delete_many(info)
                info['msg']='删除任务成功'
            try:
                os.delete_many(task['localpath'])
            except:
                print('未能成功删除本地文件')
                info['msg']='删除任务成功。但是未能成功删除本地文件'
            result.append(info)
    elif action=='restart':
        result=[]
        for gid in kwargs['gids']:
            info={'gid':gid}
            new_value={'status':1}
            down_db.update_many({'gid':gid},{'$set':new_value})
            info['msg']='更改状态成功'
            it=down_db.find_one({'gid':gid})
            user=it['user']
            remote_dir=it['remote_dir']
            cmd=u'python {} download_and_upload "{}" "{}" {} {}'.format(os.path.join(config_dir,'function.py'),1,remote_dir,user,gid)
            print(cmd)
            subprocess.Popen(cmd,shell=True)
            result.append(info)
    elif action in ['unselected','selected']:
        return None
    retdata['result']=result
    return retdata



if __name__=='__main__':
    func=sys.argv[1]
    if len(sys.argv)>2:
        args=sys.argv[2:]
        eval(func+str(tuple(args)))
    else:
        eval(func+'()')

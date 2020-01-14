from rest_framework.response import Response
from rest_framework import utils
import json, os, copy, re, jwt
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from rest_framework import status
import urllib
from django.http import QueryDict, HttpResponse, JsonResponse
from django.conf import settings
from django.core.cache import cache
from utils.utils import jwt_decode_handler,jwt_encode_handler,jwt_payload_handler,jwt_payload_handler,jwt_response_payload_handler, jwt_get_user_id_from_payload_handler
from user.models import User

'''
0 没有错误
1 未知错误  针对此错误  线上版前端弹出网络错误等公共错误
2 前端弹窗错误(包括：字段验证错误、自定义错误、账号或数据不存在、提示错误)
'''


# 将 put 请求转为 patch 请求 中间件
class PUTtoPATCHMiddleware(MiddlewareMixin):
    
    def process_request(self, request):
        if request.method == 'PUT':
            request.method = 'PATCH'


# 日志中间件
class LogMiddleware(MiddlewareMixin):
    
    def process_request(self, request):
        try:
            print('************************************************* 下面是新的一条日志 ***************************************************')
            print('拦截请求的地址：', request.path, '请求的方法：', request.method)
            print('==================================== headers 头信息 ====================================================')
            for key in request.META:
                if key[:5] == 'HTTP_':
                    print(key, request.META[key])
            print('代理IP：', request.META.get('REMOTE_ADDR'))
            print('真实IP：', request.META.get('HTTP_X_FORWARDED_FOR'))   # HTTP_X_REAL_IP
            print('==================================== request body信息 ==================================================')
            print('params参数：', request.GET)
            if request.path == '/uploadfile/':
                print('body参数：', '文件类型')
            else:
                print('body参数：', request.body.decode())
                if 'application/x-www-form-urlencoded' in request.META['CONTENT_TYPE']:
                    print('body参数：', urllib.parse.unquote(request.body.decode()))
            print('================================== View视图函数内部信息 ================================================')
        except Exception as e:
            print('发生错误：已预知的是上传文件导致，非预知错误见下：')
            print('未知错误：', e)

    def process_exception(self, request, exception):
        print('发生错误的请求地址：', request.path, '。错误原因：',exception)
        return JsonResponse({"message": "出现了无法预料的view视图错误：%s" % exception.__str__(), "errorCode": 1, "data": {}})
    
    def process_response(self,request,response):
        if type(response) == Response:
            if type(response.data) != utils.serializer_helpers.ReturnList:
                if type(response.data) == dict and (response.data.get('errorCode') and response.data.get('errorCode') != 0):
                    print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>      出现异常的日志       <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
                    print(response.data)
                    print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>      异常日志结束       <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
        if type(response) == JsonResponse:
            print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>      出现异常的日志       <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
            print(json.loads(response.content.decode()))
            print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>      异常日志结束       <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<')
        return response


# 权限 加密中间件
class PermissionMiddleware(MiddlewareMixin):
    
    def process_request(self, request):
        white_paths = ['/adminlogin/']
        if request.path not in white_paths and request.path != '/wechat/wxnotifyurl' and request.path is not '/' and not re.match(r'/swagger.*', request.path, re.I) and not re.match(r'/redoc/.*', request.path, re.I) and not re.match(r'/export.*', request.path, re.I):
            print('查看authkey',request.META.get('HTTP_AUTHKEY'))
            auth_key = request.META.get('HTTP_AUTHKEY')
            # if auth_key:
            #     print('查看秘钥：',cache.get(auth_key))
            #     if cache.get(auth_key):
            #         return JsonResponse({"message": "非法访问！已禁止操作！" , "errorCode": 10, "data": {}})
            #     cache.set(auth_key, "true", timeout=60)
            # else:
            #     return JsonResponse({"message": "非法访问！已禁止操作！" , "errorCode": 10, "data": {}})


# 格式化返回json中间件
class FormatReturnJsonMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not type(response) == HttpResponse:
            try:
                if hasattr(self, 'process_request'):
                    response = self.process_request(request)
                if not response:
                    response = self.get_response(request)
                if hasattr(self, 'process_response'):
                    response = self.process_response(request, response)
                if request.method == 'DELETE':
                    # print(response.data)
                    if response.status_code == 204:
                        response.data = {"message": '删除成功', "errorCode": 0, "data": {}}
                    else:
                        if response.data.get('detail'):
                            data = {"message": response.data.get('detail'), "errorCode": 2, "data": {}}
                        elif response.data.get('message'):
                            data = response.data
                        else:
                            data = {"message": 'error', "errorCode": 2, "data": response.data}
                        response.data = data
                    response.status_code = 200
                    response._is_rendered = False
                    response.render()
                else:
                    white_list = ['/wxnotifyurl', '/alinotifyurl']
                    if request.path is not '/' and request.path not in white_list and request.path != '/wechat/wxnotifyurl' and not re.match(r'/swagger.*', request.path, re.I) and not re.match(r'/redoc/.*', request.path, re.I) and not re.match(r'/export.*', request.path, re.I):
                        # 适配不分页返回数据的格式化
                        if type(response.data) == utils.serializer_helpers.ReturnList:
                            data = {"message": 'ok', "errorCode": 0,"data": response.data}
                            response.data = data
                        if response.data.get('detail'):
                            data = {"message": response.data.get('detail'), "errorCode": 2, "data": {}}
                            response.data = data
                        elif response.status_code > 200 and response.status_code <= 299:
                            data = {"message": 'ok', "errorCode": 0,"data": response.data}
                            response.data = data
                        elif response.status_code >= 400 and response.status_code <= 499:
                            if response.data.get('message'):  # 兼容APIView返回data的设置
                                pass
                            else:
                                data = {"message": str(response.data), "errorCode": 2,"data": response.data}
                                response.data = data
                        else:
                            if response.data.get('message'):  # 兼容APIView返回data的设置
                                pass
                            elif response.data.get('count') != None:  # 兼容分页返回data的设置
                                response.data['errorCode'] = 0
                                response.data['message'] = 'ok'
                            else:
                                data = {"message": 'ok', "errorCode": 0,
                                        "data": response.data}
                                response.data = data
                        response.status_code = 200
                        response._is_rendered = False
                        response.render()
            except Exception as e:
                print('发生错误：', e)
                if e.__str__() == "'HttpResponseNotFound' object has no attribute 'data'":
                    return JsonResponse({"message": '路径/页面未找到。', "errorCode": 2,"data": {}})
                if e.__str__() == "'JsonResponse' object has no attribute 'data'":
                    return response
                return JsonResponse({"message": "出现了无法预料的view视图错误：%s" % e.__str__(), "errorCode": 1, "data": {}})
        return response


# 冻结用户中间件
class BlockUserMiddleware(MiddlewareMixin):
    
    def process_request(self, request):
        if request.META.get('HTTP_AUTHORIZATION'):
            token = (request.META.get('HTTP_AUTHORIZATION').split(' '))[1]
            try:
                payload = jwt_decode_handler(token)
                user_id =  jwt_get_user_id_from_payload_handler(payload)
                if not user_id:
                    return JsonResponse({"message": "用户不存在！" , "errorCode": 2, "data": {}})
                now_user = User.objects.values('id', 'is_freeze').filter(id=user_id).first()
                if not now_user:
                    return JsonResponse({"message": "用户不存在！" , "errorCode": 2, "data": {}})
                if now_user.get('is_freeze'):
                    return JsonResponse({"message": "账户被冻结！", "errorCode": 2, "data": {}})
            except jwt.ExpiredSignature:
                return JsonResponse({"message": 'Token过期' , "errorCode": 2, "data": {}})
            except jwt.DecodeError:
                return JsonResponse({"message": 'Token不合法' , "errorCode": 2, "data": {}})
            except jwt.InvalidTokenError as e:
                return JsonResponse({"message": "出现了无法预料的view视图错误：%s" % e, "errorCode": 1, "data": {}})
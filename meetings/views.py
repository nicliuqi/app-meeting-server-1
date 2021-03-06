import datetime
import json
import random
import requests
import logging
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from drf_yasg.utils import swagger_auto_schema
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin, RetrieveModelMixin, DestroyModelMixin, \
    UpdateModelMixin
from rest_framework_simplejwt import authentication
from meetings.models import User, Group, Meeting, GroupUser
from meetings.permissions import MaintainerPermission, AdminPermission
from meetings.serializers import LoginSerializer, GroupsSerializer, MeetingSerializer, UsersSerializer, \
    UserSerializer, GroupUserAddSerializer, GroupSerializer, UsersInGroupSerializer, \
    UserGroupSerializer, MeetingListSerializer, GroupUserDelSerializer, MeetingDataSerializer, UserInfoSerializer

logger = logging.getLogger('log')


class LoginView(GenericAPIView, CreateModelMixin, ListModelMixin):
    """用户注册与授权登陆"""
    serializer_class = LoginSerializer
    queryset = User.objects.all()

    @swagger_auto_schema(operation_summary='用户注册与授权登陆')
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()


class GroupsView(GenericAPIView, ListModelMixin):
    """查询所有SIG组"""
    serializer_class = GroupsSerializer
    queryset = Group.objects.all()
    filter_backends = [SearchFilter]
    search_fields = ['group_name']

    @swagger_auto_schema(operation_summary='查询所有SIG组')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class GroupView(GenericAPIView, RetrieveModelMixin):
    """查询单个SIG组"""
    serializer_class = GroupSerializer
    queryset = Group.objects.all()

    @swagger_auto_schema(operation_summary='查询单个SIG组')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class UsersIncludeView(GenericAPIView, ListModelMixin):
    """查询所选SIG组的所有成员"""
    serializer_class = UsersInGroupSerializer
    queryset = User.objects.all()
    filter_backends = [SearchFilter]
    search_fields = ['nickname']

    @swagger_auto_schema(operation_summary='查询所选SIG组的所有成员')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            groupusers = GroupUser.objects.filter(group_id=self.kwargs['pk']).all()
            ids = [x.user_id for x in groupusers]
            user = User.objects.filter(id__in=ids)
            return user
        except KeyError:
            pass


class UsersExcludeView(GenericAPIView, ListModelMixin):
    """查询不在该组的所有成员"""
    serializer_class = UsersSerializer
    queryset = User.objects.all().order_by('nickname')
    filter_backends = [SearchFilter]
    search_fields = ['nickname']

    @swagger_auto_schema(operation_summary='查询不在该组的所有用户')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            groupusers = GroupUser.objects.filter(group_id=self.kwargs['pk']).all()
            ids = [x.user_id for x in groupusers]
            user = User.objects.filter().exclude(id__in=ids)
            return user
        except KeyError:
            pass


class UserGroupView(GenericAPIView, ListModelMixin):
    """查询该用户的SIG组以及该组的etherpad"""
    serializer_class = UserGroupSerializer
    queryset = GroupUser.objects.all()

    @swagger_auto_schema(operation_summary='查询该用户的SIG组以及该组的etherpad')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            usergroup = GroupUser.objects.filter(user_id=self.kwargs['pk']).all()
            return usergroup
        except KeyError:
            pass


class UserView(GenericAPIView, UpdateModelMixin):
    """更新用户gitee_name"""
    serializer_class = UserSerializer
    queryset = User.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (AdminPermission,)

    @swagger_auto_schema(operation_summary='更新用户gitee_name')
    def put(self, request, *args, **kwargs):
        id = kwargs.get('pk')
        gitee_name = request.data['gitee_name']
        # 有gitee_name,若gitee_name重复则返回；不重复则更新用户信息并将level置为2;gitee_name不存在则将gitee_name置空，level改为1
        if gitee_name:
            if User.objects.filter(gitee_name=gitee_name):
                return JsonResponse({'code': 400, 'msg': 'gitee_name重复'})
            # print(User.objects.get(gitee_name=gitee_name))
            if User.objects.filter(id=id, level=3):
                User.objects.filter(id=id).update(gitee_name=gitee_name)
            else:
                User.objects.filter(id=id).update(gitee_name=gitee_name, level=2)
        else:
            User.objects.filter(id=id).update(gitee_name=gitee_name, level=1)
        return self.update(request, *args, **kwargs)


class GroupUserAddView(GenericAPIView, CreateModelMixin):
    """SIG组批量新增成员"""
    serializer_class = GroupUserAddSerializer
    queryset = GroupUser.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (AdminPermission,)

    @swagger_auto_schema(operation_summary='SIG组批量新增成员')
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class GroupUserDelView(GenericAPIView, CreateModelMixin):
    """批量删除组成员"""
    serializer_class = GroupUserDelSerializer
    queryset = GroupUser.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (AdminPermission,)

    def post(self, request, *args, **kwargs):
        group_id = self.request.data.get('group_id')
        ids = self.request.data.get('ids')
        ids_list = [int(x) for x in ids.split('-')]
        GroupUser.objects.filter(group_id=group_id, user_id__in=ids_list).delete()
        return JsonResponse({'code': 204, 'msg': '删除成功'})


class MeetingsWeeklyView(GenericAPIView, ListModelMixin):
    """查询前后一周的所有会议"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.filter(Q(is_delete=0) & (Q(
        date__gte=str(datetime.datetime.now() - datetime.timedelta(days=7))[:10]) & Q(
        date__lte=str(datetime.datetime.now() + datetime.timedelta(days=7))[:10])))
    filter_backends = [SearchFilter]
    search_fields = ['topic', 'group_name']

    @swagger_auto_schema(operation_summary='查询未来一周的所有会议')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class MeetingsDailyView(GenericAPIView, ListModelMixin):
    """查询本日的所有会议"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.all().filter(Q(is_delete=0) & Q(date__exact=str(datetime.datetime.now())[:10]))

    @swagger_auto_schema(operation_summary='查询本日的所有会议')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class MeetingsView(GenericAPIView, CreateModelMixin):
    """创建会议"""
    serializer_class = MeetingSerializer
    queryset = Meeting.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (MaintainerPermission,)

    @swagger_auto_schema(operation_summary='创建会议')
    def post(self, request, *args, **kwargs):

        host_dict = settings.MEETING_HOSTS
        host_list = list(host_dict.values())
        random.shuffle(host_list)
        for host in list(host_list):
            headers = {
                "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)
            }
            # print(headers)
            res = requests.get("https://api.zoom.us/v2/users/{}/meetings".format(host), headers=headers)
            # 将查询出的所有会议的id放入一个list
            if res:
                meetings_id_list = []
                for meeting in res.json()['meetings']:
                    meetings_id_list.append(meeting['id'])

                # 遍历meetings_id_list，用meeting_id查询单个会议具体信息，若该会议处于开启状态，则查出该会议对应的host，并从随机hosts中排除掉
                for meeting_id in meetings_id_list:
                    url = "https://api.zoom.us/v2/meetings/{}".format(meeting_id)
                    headers = {
                        "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)}

                    response = requests.request("GET", url, headers=headers)
                    if response.json()['status'] == 'started':
                        del host_dict[response.json()['host_id']]
                        break
            else:
                return JsonResponse({'code': 1002, 'massage': '请求失败，请重试'})

        if len(host_dict) == 0:
            return JsonResponse({'code': 1000, 'massage': '暂无可用host,请稍后再试'})
        # 随机取一个可用的host
        host_email = random.choice(list(host_dict.values()))
        # 发送post请求，创建会议
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)
        }
        try:
            data = self.request.data
            date = data['date']
            start = data['start']
            end = data['end']
            user_id = request.user.id
            group_id = data['group_id']
        except Exception as e:
            logger.error(e)
            return JsonResponse({'code': 1000, 'massage': '创建会议条件不足'})
        if start >= end:
            return JsonResponse({'code': 1001, 'massage': '请输入正确的结束时间'})
        start_time = date + 'T' + start + 'Z'
        duration = (int(end[:2]) - int(start[:2])) * 60 + (int(end[3:5]) - int(start[3:5]))
        new_data = {}
        new_data['start_time'] = start_time
        new_data['duration'] = duration
        url = "https://api.zoom.us/v2/users/{}/meetings".format(host_email)
        response = requests.post(url, data=json.dumps(new_data), headers=headers).json()
        # 数据库生成数据
        Meeting.objects.create(
            mid=response['id'],
            topic=data['topic'],
            sponsor=data['sponsor'],
            group_name=data['group_name'],
            date=date,
            start=start,
            end=end,
            etherpad=data['etherpad'],
            emaillist=data['emaillist'] if 'emaillist' in data else '',
            timezone=response['timezone'],
            agenda=data['agenda'] if 'agenda' in data else '',
            host_id=response['host_id'],
            join_url=response['join_url'],
            start_url=response['start_url'],
            user_id=user_id,
            group_id=group_id
        )
        # 返回请求数据
        resp = {'code': 201, 'massage': '创建成功'}
        meeting = Meeting.objects.get(mid=response['id'])
        resp['id'] = meeting.id
        return JsonResponse(resp)


class MeetingView(GenericAPIView, RetrieveModelMixin):
    """查询会议(id)"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.all()

    @swagger_auto_schema(operation_summary='查询会议')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class MeetingDelView(GenericAPIView, DestroyModelMixin):
    """删除会议(mid)"""
    serializer_class = MeetingSerializer
    queryset = Meeting.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (MaintainerPermission,)

    @swagger_auto_schema(operation_summary='删除会议')
    def delete(self, request, *args, **kwargs):
        mid = kwargs.get('mid')
        try:
            url = "https://api.zoom.us/v2/meetings/{}".format(mid)
            headers = {
                "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)}
            requests.request("DELETE", url, headers=headers)
        except:
            pass
        # 无论zoom接口删除成功或会议不存在，数据库作逻辑删除
        Meeting.objects.filter(mid=mid).update(is_delete=1)
        return JsonResponse({"code": 204, "massege": "Delete successfully."})


class UserInfoView(GenericAPIView, RetrieveModelMixin):
    serializer_class = UserInfoSerializer
    queryset = User.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)

    def get(self, request, *args, **kwargs):
        user_id = kwargs.get('pk')
        if user_id != request.user.id:
            logger.warning('user_id:{}, request.user.id:{}'.format(user_id, request.user.id))
            return JsonResponse({"code": 400, "massage": "错误操作，信息不匹配！"})
        return self.retrieve(request, *args, **kwargs)

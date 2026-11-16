from django.urls import path
from .views import AcessosDashboard, CriarUsuario, UsuariosGET, enroll_fingerprint, verify_fingerprint

urlpatterns = [
    path('login/', UsuariosGET.as_view()),                       # login por e-mail e senha
    path('criarUsuario/', CriarUsuario.as_view()),               # cadastro sem digital
    path('enroll/', enroll_fingerprint, name='enroll_fingerprint'),  # cadastro com digital
    path('verify/', verify_fingerprint, name='verify_fingerprint'),  # login com digital
    path('acessos/', AcessosDashboard.as_view(), name='acessos_dashboard'),
]

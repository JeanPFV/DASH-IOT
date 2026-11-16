from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from .models import Usuarios

class UsuariosSeriliazer(serializers.ModelSerializer):
    class Meta:
        model = Usuarios
        fields = ['id', 'nome', 'email', 'senha', 'digital']
        # A senha entra no cadastro, mas nunca volta nas respostas da API
        extra_kwargs = {'senha': {'write_only': True}}

    def create(self, validated_data):
        validated_data['senha'] = make_password(validated_data['senha'])
        return super().create(validated_data)

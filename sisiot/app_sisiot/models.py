from django.db.models import JSONField
from django.db import models

# As tabelas são criadas pelo supabase_schema.sql (managed = False),
# então o Django só lê e grava nelas.

class Usuarios (models.Model):
    id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=50)
    email = models.CharField(max_length=50, unique=True)
    senha = models.CharField(max_length=255)
    # {"slot": 5, "cadastrada_em": "..."} -> o template fica guardado só dentro do sensor
    digital = JSONField(null=True, blank=True)

    class Meta:
        db_table = 'usuarios'
        managed = False

class Acessos (models.Model):
    """Cada tentativa de entrar no site (digital ou senha). Alimenta o dashboard."""
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(Usuarios, models.SET_NULL, null=True, blank=True, db_column='usuario_id')
    metodo = models.CharField(max_length=10)          # 'digital' ou 'senha'
    sucesso = models.BooleanField()
    confianca = models.IntegerField(null=True, blank=True)
    detalhe = models.CharField(max_length=120, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'acessos'
        managed = False

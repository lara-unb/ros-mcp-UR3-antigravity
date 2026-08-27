# Scripts dos robôs

Organize os scripts por robô e ambiente de execução:

```text
scripts/robots/
└── <robô>/
    ├── real/
    ├── ursim/
    ├── coppeliasim/
    └── shared/
```

Use `real/`, `ursim/` e `coppeliasim/` para códigos específicos de cada
ambiente. Coloque em `shared/` somente funções que possam ser usadas com
segurança pelos ambientes correspondentes.

Os scripts operacionais do projeto, como inicialização do Docker e entrada do
container, ficam na pasta raiz `shell/`.
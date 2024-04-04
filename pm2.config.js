module.exports = {
  apps: [
    {
      name: 'BG_REMOVER_5002',
      script: 'main.py',
      interpreter: 'python3',
      args: 'serve --port 5002',
      watch: true,
      env: {
        MODE: 'production',
      },
    },
    {
      name: 'BG_REMOVER_5003',
      script: 'main.py',
      interpreter: 'python3',
      args: 'serve --port 5003',
      watch: true,
      env: {
        MODE: 'production',
      },
    },
    {
      name: 'BG_REMOVER_5004',
      script: 'main.py',
      interpreter: 'python3',
      args: 'serve --port 5004',
      watch: true,
      env: {
        MODE: 'production',
      },
    },
  ],
};

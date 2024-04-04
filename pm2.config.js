module.exports = {
  apps: [
    {
      name: 'BG_REMOVER_5002',
      script: 'gunicorn',
      interpreter: 'python3',
      args: 'main:app -w 4 -b 0.0.0.0:5002',
      watch: true,
      env: {
        MODE: 'production',
      },
    },
  ],
};

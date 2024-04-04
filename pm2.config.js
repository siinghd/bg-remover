module.exports = {
  apps: [
    {
      name: 'BG_REMOVER',
      script: 'main.py',
      args: '',
      interpreter: 'python3',
      exec_mode: 'cluster',
      instances: 'max', 
      env: {
        MODE: 'production', 
      },
    },
  ],
};

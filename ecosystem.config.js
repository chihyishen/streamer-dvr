module.exports = {
  apps: [
    {
      name: "streamer-dvr",
      script: ".venv/bin/python",
      args: "-m app.main",
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "streamer-dvr-worker",
      script: ".venv/bin/python",
      args: "-m app.worker",
      interpreter: "none",
      autorestart: true,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    }
  ],
};

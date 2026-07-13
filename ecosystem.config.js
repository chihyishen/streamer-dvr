module.exports = {
  apps: [
    {
      name: "streamer-dvr",
      cwd: __dirname,
      script: ".venv/bin/python",
      args: "-m app.main",
      interpreter: "none",
      autorestart: true,
      watch: false,
      out_file: "logs/api.out.log",
      error_file: "logs/api.err.log",
      log_type: "raw",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "streamer-dvr-worker",
      cwd: __dirname,
      script: ".venv/bin/python",
      args: "-m app.worker",
      interpreter: "none",
      autorestart: true,
      watch: false,
      out_file: "logs/worker.out.log",
      error_file: "logs/worker.err.log",
      log_type: "raw",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    }
  ],
};

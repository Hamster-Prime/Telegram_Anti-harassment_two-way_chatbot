use anyhow::{Result, Context};
use std::sync::Arc;
use std::process::Command;
use tracing::{info, warn, error};

use crate::config::Config;

pub struct NetworkTestService {
    config: Arc<Config>,
}

impl NetworkTestService {
    pub fn new(config: &Arc<Config>) -> Self {
        Self {
            config: config.clone(),
        }
    }

    /// 执行Ping测试
    pub async fn ping(&self,
        target: &str,
        count: Option<i32>,
    ) -> Result<String> {
        let count = count.unwrap_or(4);

        // 本地执行ping
        let output = Command::new("ping")
            .args([&format!("-c{}", count), target])
            .output()
            .context("执行ping命令失败")?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() {
            Ok(format!("Ping测试结果:\n```\n{}\n```", stdout))
        } else {
            anyhow::bail!("Ping失败: {}", stderr)
        }
    }

    /// 执行路由追踪（使用nexttrace或traceroute）
    pub async fn traceroute(&self,
        target: &str,
        use_tcp: bool,
    ) -> Result<String> {
        // 首先尝试使用nexttrace
        if let Ok(result) = self.run_nexttrace(target, use_tcp).await {
            return Ok(result);
        }

        // 回退到系统traceroute
        self.run_system_traceroute(target).await
    }

    async fn run_nexttrace(
        &self,
        target: &str,
        use_tcp: bool,
    ) -> Result<String> {
        let mut args = vec![target];
        if use_tcp {
            args.push("-T");
        }

        let output = Command::new("nexttrace")
            .args(&args)
            .output()
            .context("执行nexttrace失败")?;

        let stdout = String::from_utf8_lossy(&output.stdout);

        if output.status.success() {
            Ok(format!("路由追踪结果:\n```\n{}\n```", stdout))
        } else {
            anyhow::bail!("Nexttrace执行失败")
        }
    }

    async fn run_system_traceroute(
        &self,
        target: &str,
    ) -> Result<String> {
        let cmd = if cfg!(target_os = "linux") {
            "traceroute"
        } else {
            "traceroute"
        };

        let output = Command::new(cmd)
            .args([&format!("-m30"), target]) // 最大30跳
            .output()
            .context("执行traceroute失败")?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() || !stdout.is_empty() {
            Ok(format!("路由追踪结果:\n```\n{}\n```", stdout))
        } else {
            anyhow::bail!("Traceroute失败: {}", stderr)
        }
    }

    /// 通过SSH在远程服务器执行命令
    pub async fn remote_command(
        &self,
        command: &str,
    ) -> Result<String> {
        let host = self.config.remote_ssh_host.as_ref()
            .context("未配置远程SSH主机")?;
        let user = self.config.remote_ssh_user.as_ref()
            .context("未配置远程SSH用户")?;
        let port = self.config.remote_ssh_port;
        let key_path = self.config.remote_ssh_key_path.as_ref();

        let mut cmd = Command::new("ssh");
        cmd.arg("-o")
            .arg("StrictHostKeyChecking=no")
            .arg("-o")
            .arg("ConnectTimeout=10")
            .arg("-p")
            .arg(port.to_string())
            .arg(format!("{}@{}", user, host));

        if let Some(key) = key_path {
            cmd.arg("-i").arg(key);
        }

        cmd.arg(command);

        let output = cmd.output().context("SSH命令执行失败")?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() {
            Ok(format!("远程执行结果:\n```\n{}\n```", stdout))
        } else {
            anyhow::bail!("远程命令失败: {}", stderr)
        }
    }

    /// 远程Ping测试
    pub async fn remote_ping(
        &self,
        target: &str,
    ) -> Result<String> {
        let cmd = format!("ping -c4 {}", target);
        self.remote_command(&cmd).await
    }

    /// 远程路由追踪
    pub async fn remote_traceroute(
        &self,
        target: &str,
    ) -> Result<String> {
        let cmd = format!("traceroute -m30 {}", target);
        self.remote_command(&cmd).await
    }

    /// TCP端口测试
    pub async fn tcp_ping(
        &self,
        target: &str,
        port: u16,
    ) -> Result<String> {
        use std::net::TcpStream;
        use std::time::Instant;

        let addr = format!("{}:{}", target, port);
        let start = Instant::now();

        match TcpStream::connect(&addr) {
            Ok(_) => {
                let elapsed = start.elapsed();
                Ok(format!(
                    "TCP端口测试成功\n目标: {}\n端口: {}\n连接时间: {:?}",
                    target, port, elapsed
                ))
            }
            Err(e) => {
                anyhow::bail!("TCP连接失败: {}", e)
            }
        }
    }
}

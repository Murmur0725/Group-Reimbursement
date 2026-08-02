function updateBatchStatus(target, job) {
  if (!target) return;

  const statusList = target.closest(".batch-status-list");
  if (statusList) {
    statusList.hidden = false;
    statusList.style.display = "block";
  }
  target.hidden = false;
  target.classList.add("is-visible");

  const text = target.querySelector(".batch-status-text");
  const progress = target.querySelector("progress");
  const files = target.querySelector(".batch-status-files");
  const total = job.total || Number(target.dataset.total || 0);
  const max = total || 1;

  progress.max = max;
  progress.value = Math.min(job.processed || 0, max);

  const statusText = {
    queued: "等待处理",
    running: "处理中",
    completed: "处理完成",
    failed: "处理失败",
  }[job.status] || job.status;

  text.textContent = `${job.title}：${statusText}，已处理 ${job.processed || 0}/${total} 条，跳过 ${job.skipped || 0} 条。${job.message || ""}`;

  files.innerHTML = "";
  if (job.files && job.files.length > 0) {
    for (const file of job.files) {
      const link = document.createElement("a");
      link.href = file.download_url;
      link.textContent = file.file_name;
      files.appendChild(link);
    }
  }

  target.classList.toggle("is-running", job.status === "queued" || job.status === "running");
  target.classList.toggle("is-failed", job.status === "failed");
  target.classList.toggle("is-completed", job.status === "completed");
}

async function pollBatchJob(jobId, target) {
  const response = await fetch(`/actions/batch-jobs/${jobId}`);
  if (!response.ok) {
    throw new Error("无法读取批量任务状态");
  }
  const job = await response.json();
  updateBatchStatus(target, job);
  if (job.status === "queued" || job.status === "running") {
    window.setTimeout(() => pollBatchJob(jobId, target), 1000);
  }
}

document.addEventListener("submit", async (event) => {
  const form = event.target.closest(".batch-job-form");
  if (!form) return;

  event.preventDefault();
  const target = document.getElementById(form.dataset.statusTarget);
  const button = form.querySelector("button");
  if (button) button.disabled = true;

  try {
    const response = await fetch(form.dataset.jobUrl, { method: "POST" });
    if (!response.ok) {
      throw new Error("无法启动批量任务");
    }
    const job = await response.json();
    updateBatchStatus(target, job);
    await pollBatchJob(job.id, target);
  } catch (error) {
    if (target) {
      const text = target.querySelector(".batch-status-text");
      if (text) text.textContent = error.message;
      target.classList.add("is-failed");
    }
  } finally {
    if (button) button.disabled = false;
  }
});

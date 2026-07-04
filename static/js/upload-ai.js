(function () {
  const fileInput = document.getElementById("file");
  const dropZone = document.getElementById("dropZone");
  const fileInfo = document.getElementById("fileInfo");
  const fileName = document.getElementById("fileName");
  const fileSize = document.getElementById("fileSize");
  const removeFile = document.getElementById("removeFile");
  const uploadPlaceholder = document.querySelector(".upload-placeholder");
  const analyzeBtn = document.getElementById("analyzeBtn");
  const analyzeStatus = document.getElementById("analyzeStatus");

  let currentFile = null;

  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function showFile(f) {
    currentFile = f;
    fileName.textContent = f.name;
    fileSize.textContent = fmtSize(f.size);
    uploadPlaceholder.style.display = "none";
    fileInfo.style.display = "flex";
    if (analyzeBtn) analyzeBtn.style.display = "inline-flex";
  }

  function hideFile() {
    currentFile = null;
    fileInput.value = "";
    uploadPlaceholder.style.display = "block";
    fileInfo.style.display = "none";
    if (analyzeBtn) analyzeBtn.style.display = "none";
    if (analyzeStatus) analyzeStatus.style.display = "none";
  }

  fileInput.addEventListener("change", function () {
    if (this.files.length > 0) showFile(this.files[0]);
  });

  if (removeFile) {
    removeFile.addEventListener("click", function (e) {
      e.stopPropagation();
      hideFile();
    });
  }

  dropZone.addEventListener("dragover", function (e) {
    e.preventDefault();
    this.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", function (e) {
    e.preventDefault();
    this.classList.remove("dragover");
  });
  dropZone.addEventListener("drop", function (e) {
    e.preventDefault();
    this.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      showFile(e.dataTransfer.files[0]);
    }
  });
  dropZone.addEventListener("click", function () {
    fileInput.click();
  });

  // --- AI Analysis ---
  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", async function () {
      if (!currentFile) return;

      const formData = new FormData();
      formData.append("file", currentFile);

      analyzeBtn.disabled = true;
      analyzeBtn.innerHTML =
        '<i class="ri-upload-cloud-2-line spinning"></i> 上传文件中...';

      let analyzingTimer;
      function setStatus(stage, msg) {
        if (!analyzeStatus) return;
        analyzeStatus.style.display = "flex";
        const el = analyzeStatus;
        const icon = el.querySelector("i");
        const text = el.querySelector(".status-text");
        if (stage === "uploading") {
          el.className = "analyze-status";
          icon.className = "ri-upload-cloud-2-line spinning";
          text.textContent = "正在上传文件到服务器...";
          analyzingTimer = setTimeout(function () {
            setStatus("analyzing");
          }, 1500);
        } else if (stage === "analyzing") {
          el.className = "analyze-status";
          icon.className = "ri-loader-4-line spinning";
          text.textContent = "AI 正在分析文件内容...";
        } else if (stage === "success") {
          clearTimeout(analyzingTimer);
          el.className = "analyze-status success";
          icon.className = "ri-check-line";
          text.textContent = "AI 分析完成，已自动填充表单";
        } else if (stage === "error") {
          clearTimeout(analyzingTimer);
          el.className = "analyze-status error";
          icon.className = "ri-close-circle-line";
          text.textContent = msg;
        }
      }

      setStatus("uploading");

      try {
        console.log("Uploading file for analysis:", currentFile.name);
        const res = await fetch("/resource/analyze", {
          method: "POST",
          headers: { "X-CSRF-Token": (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute("content") || "" },
          body: formData,
        });
        const json = await res.json();

        if (!json.success) {
          setStatus("error", json.error || "分析失败");
          return;
        }

        const data = json.data;

        if (data.title) {
          document.getElementById("title").value = data.title;
        }
        if (data.description) {
          document.getElementById("description").value = data.description;
        }

        if (data.category_ids) {
          for (const [slug, catId] of Object.entries(data.category_ids)) {
            const sel = document.getElementById("cat_" + slug);
            if (sel) {
              for (const opt of sel.options) {
                if (opt.value == catId) {
                  opt.selected = true;
                  break;
                }
              }
            }
          }
        }

        setStatus("success");
      } catch (err) {
        if (err.message.includes("InvalidParameter")) {
          setStatus("error", "仅支持分析 PDF 文件");
        } else {
          setStatus("error", "网络错误: " + err.message);
        }
      } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = '<i class="ri-sparkling-line"></i> AI 智能分析';
      }
    });
  }
})();

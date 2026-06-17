/* EchoMind session — drives the live interview */

(function () {
  "use strict";

  var sid = window.ECHOMIND_SESSION_ID;
  if (!sid) return;

  var form = document.getElementById("answer-form");
  var input = document.getElementById("answer-input");
  var transcript = document.getElementById("transcript");
  var progressItems = document.querySelectorAll(".progress-list li");

  if (!form || !input || !transcript) return;

  // Heuristic keywords to mark progress
  var topicKeywords = {
    childhood: ["child", "born", "grew up", "mother", "father", "parents", "home", "wales", "cardiff"],
    school: ["school", "teacher", "class", "lesson", "learned", "pupil", "headmaster"],
    love: ["love", "wife", "husband", "kiss", "marriage", "married", "dance", "romance"],
    career: ["work", "job", "teaching", "nurse", "doctor", "office", "profession", "career"],
    proud: ["proud", "achievement", "accomplished"],
    hardships: ["hard", "loss", "died", "war", "illness", "difficult", "suffered"],
    wisdom: ["advice", "wisdom", "grandchild", "remember", "future"]
  };

  function scrollToBottom() {
    transcript.scrollTop = transcript.scrollHeight;
  }

  function appendBubble(role, content) {
    var div = document.createElement("div");
    div.className = "bubble bubble-" + (role === "user" ? "user" : "assistant");
    var label = document.createElement("div");
    label.className = "bubble-label";
    label.textContent = role === "user" ? "You" : "Interviewer";
    var body = document.createElement("div");
    body.className = "bubble-body";
    body.textContent = content;
    div.appendChild(label);
    div.appendChild(body);
    transcript.appendChild(div);
    scrollToBottom();
  }

  function markTopics(message) {
    if (!message) return;
    var lower = message.toLowerCase();
    progressItems.forEach(function (li) {
      var topic = li.getAttribute("data-topic");
      if (!topic) return;
      var kws = topicKeywords[topic] || [];
      if (kws.some(function (k) { return lower.indexOf(k) !== -1; })) {
        li.classList.add("done");
        var dot = li.querySelector(".dot");
        if (dot) dot.innerHTML = "&#10003;";
      }
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var msg = (input.value || "").trim();
    if (!msg) return;

    appendBubble("user", msg);
    markTopics(msg);
    input.value = "";
    input.disabled = true;
    var btn = form.querySelector("button");
    if (btn) btn.disabled = true;

    fetch("/session/" + sid + "/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.question) {
          appendBubble("assistant", data.question);
        }
        if (data.complete) {
          // Show a brief completion message, then redirect
          setTimeout(function () {
            window.location.href = "/session/" + sid + "/waiting";
          }, 1800);
        } else {
          input.disabled = false;
          if (btn) btn.disabled = false;
          input.focus();
        }
      })
      .catch(function () {
        input.disabled = false;
        if (btn) btn.disabled = false;
        appendBubble("assistant", "(The interviewer is having a quiet moment. Please try again.)");
      });
  });

  scrollToBottom();
})();

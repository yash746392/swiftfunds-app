// Animate balance on dashboard
function animateBalance(balance) {
    let displayed = 0;
    const step = balance / 100;
    const balEl = document.getElementById('balance');

    if (!balEl) return;

    const animate = setInterval(() => {
        displayed += step;
        if(displayed >= balance) {
            balEl.textContent = balance.toFixed(2);
            clearInterval(animate);
        } else {
            balEl.textContent = displayed.toFixed(2);
        }
    }, 10);
}

// Run on page load
document.addEventListener("DOMContentLoaded", () => {
    const balEl = document.getElementById('balance');
    if(balEl) {
        const balance = parseFloat(balEl.dataset.value);
        animateBalance(balance);
    }
});

// Particle background (particles.js)
particlesJS("particles-js", {
  "particles": {
    "number": { "value": 80 },
    "size": { "value": 3 },
    "color": { "value": "#ffffff" },
    "line_linked": { "enable": true, "distance": 150, "color": "#ffffff", "opacity": 0.4 },
    "move": { "speed": 2 }
  },
  "interactivity": {
    "events": { "onhover": { "enable": true, "mode": "repulse" } }
  }
});

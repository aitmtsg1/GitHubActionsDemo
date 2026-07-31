// Simple calculator logic using Shunting-yard + RPN evaluation
// Handles + - * / and parentheses, decimals, percent, backspace, clear, keyboard input.

const display = document.getElementById('display');
const keys = document.querySelector('.keys');

function updateDisplay(v){
  display.value = v;
}

// Utilities
const isOperator = c => ['+','-','*','/'].includes(c);

// Tokenize input string into numbers, operators, parentheses
function tokenize(expr){
  const tokens = [];
  let i = 0;
  while(i < expr.length){
    const ch = expr[i];
    if(ch === ' ') { i++; continue; }
    // number (may be negative if unary minus)
    if((ch >= '0' && ch <= '9') || ch === '.'
       || (ch === '-' && (i === 0 || isOperator(expr[i-1]) || expr[i-1] === '(') && (expr[i+1] && (/\d|\./).test(expr[i+1])))){
      let j = i;
      // include unary minus in number
      if(expr[j] === '-') j++;
      while(j < expr.length && (expr[j] >= '0' && expr[j] <= '9' || expr[j] === '.')) j++;
      tokens.push(expr.slice(i, j));
      i = j;
      continue;
    }
    if(isOperator(ch) || ch === '(' || ch === ')'){
      tokens.push(ch);
      i++;
      continue;
    }
    // ignore unknown characters
    i++;
  }
  return tokens;
}

function shuntingYard(tokens){
  const output = [];
  const ops = [];
  const prec = { '+':1, '-':1, '*':2, '/':2 };
  tokens.forEach(t => {
    if(!isNaN(Number(t))){ output.push(t); return; }
    if(isOperator(t)){
      while(ops.length){
        const top = ops[ops.length-1];
        if(isOperator(top) && ((prec[top] > prec[t]) || (prec[top] === prec[t]))){
          output.push(ops.pop());
        } else break;
      }
      ops.push(t);
      return;
    }
    if(t === '('){ ops.push(t); return; }
    if(t === ')'){
      while(ops.length && ops[ops.length-1] !== '('){
        output.push(ops.pop());
      }
      if(ops.length && ops[ops.length-1] === '(') ops.pop();
      return;
    }
  });
  while(ops.length) output.push(ops.pop());
  return output;
}

function evaluateRPN(rpn){
  const stack = [];
  for(const t of rpn){
    if(!isNaN(Number(t))){ stack.push(Number(t)); continue; }
    const b = stack.pop();
    const a = stack.pop();
    if(a === undefined || b === undefined) return NaN;
    let res = NaN;
    switch(t){
      case '+': res = a + b; break;
      case '-': res = a - b; break;
      case '*': res = a * b; break;
      case '/': res = b === 0 ? NaN : a / b; break;
    }
    stack.push(res);
  }
  return stack.length === 1 ? stack[0] : NaN;
}

function safeEval(expr){
  try{
    const tokens = tokenize(expr);
    const rpn = shuntingYard(tokens);
    const result = evaluateRPN(rpn);
    if(!isFinite(result) || isNaN(result)) return 'Error';
    // trim floating noise
    const rounded = Math.round((result + Number.EPSILON) * 1e12)/1e12;
    return String(rounded);
  } catch(e){
    return 'Error';
  }
}

// UI actions
keys.addEventListener('click', (ev) => {
  const btn = ev.target.closest('button');
  if(!btn) return;
  const text = btn.textContent.trim();
  if(btn.dataset.action === 'clear'){
    updateDisplay('');
    return;
  }
  if(btn.dataset.action === 'back'){
    updateDisplay(display.value.slice(0, -1));
    return;
  }
  if(btn.dataset.action === 'dot'){
    // prevent two dots in the current number
    const val = display.value;
    // find last token
    let lastChunk = '';
    for(let i=val.length-1; i>=0; i--){
      const ch = val[i];
      if(isOperator(ch) || ch === '(' || ch === ')') break;
      lastChunk = ch + lastChunk;
    }
    if(!lastChunk.includes('.')) updateDisplay(val + '.');
    return;
  }
  if(btn.dataset.action === 'percent'){
    // convert current trailing number to percentage
    const val = display.value;
    // find last token start
    let i = val.length - 1;
    while(i >=0 && (val[i] === '.' || (val[i] >= '0' && val[i] <= '9') || (val[i] === '-' && (i===0 || isOperator(val[i-1]) || val[i-1] === '(')))) i--;
    const last = val.slice(i+1);
    if(last.length === 0) return;
    const num = Number(last);
    if(isNaN(num)) return;
    const replaced = val.slice(0, i+1) + String(num / 100);
    updateDisplay(replaced);
    return;
  }
  if(btn.dataset.action === 'paren'){
    // simple toggle: insert '(' if number of open <= close, else insert ')'
    const val = display.value;
    const opens = (val.match(/\(/g) || []).length;
    const closes = (val.match(/\)/g) || []).length;
    if(opens <= closes) updateDisplay(val + '(');
    else updateDisplay(val + ')');
    return;
  }
  if(btn.dataset.op){
    updateDisplay(display.value + btn.dataset.op);
    return;
  }
  if(btn.dataset.action === 'equals' || text === '='){
    const res = safeEval(display.value);
    updateDisplay(res);
    return;
  }
  // default: number or other character
  updateDisplay(display.value + text);
});

// Keyboard support
window.addEventListener('keydown', (e) => {
  const allowed = '0123456789+-*/().%';
  if(e.key === 'Enter' || e.key === '='){
    e.preventDefault();
    const res = safeEval(display.value);
    updateDisplay(res);
    return;
  }
  if(e.key === 'Backspace'){
    e.preventDefault();
    updateDisplay(display.value.slice(0, -1));
    return;
  }
  if(e.key === 'Escape'){
    e.preventDefault();
    updateDisplay('');
    return;
  }
  if(allowed.includes(e.key)){
    e.preventDefault();
    // translate '*' and '/' etc are fine. For percent key, insert '%'
    if(e.key === '%'){
      // trigger percent transformation immediately
      const btn = document.querySelector('[data-action="percent"]');
      btn && btn.click();
      return;
    }
    updateDisplay(display.value + e.key);
    return;
  }
});

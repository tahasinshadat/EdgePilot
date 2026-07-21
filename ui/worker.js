self.onmessage = function(e) {
  const messages = e.data;
  const processed = messages.map(msg => {
    let html = (msg.content || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
      
    // Format bullet points
    html = html.replace(/^[\s]*[-*][\s]+(.*)$/gm, '<li>$1</li>');
    
    // Wrap consecutive li elements in ul (allowing any whitespace/newlines between them)
    html = html.replace(/(<li>[\s\S]*?<\/li>(?:[\s]*<li>[\s\S]*?<\/li>)*)/g, '<ul>$1</ul>');
    
    // Remove newlines that are inside <ul> elements so they don't get turned into <br />
    html = html.replace(/<ul>([\s\S]*?)<\/ul>/g, function(match, inner) {
        return '<ul>' + inner.replace(/\n/g, '') + '</ul>';
    });
    
    // Format code blocks
    html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Format headers
    html = html.replace(/^#### (.*)$/gm, '<h4>$1</h4>');
    html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.*)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.*)$/gm, '<h1>$1</h1>');
    
    // Format bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Format italics
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    html = html.replace(/\n/g, '<br />');
    
    return {
      role: msg.role,
      html: html
    };
  });
  
  self.postMessage(processed);
};

# Mini-Project 3: Build an Advanced AI Finance Tool (n8n or your platform)

From building tools to building SMART tools

---

## The Assignment

Build a more advanced AI finance tool using n8n or another platform of your choice. It should analyze, explain, and/or advise on financial decisions—using AI as the brain.

**Timeline:** One week from Session 10

**Submission:** No public link required. Present your tool via a video demo showing your workflow (nodes, prompts, logic) and the tool in action. Keep API keys private.

Reference tutorial: [Build an Financial AI tool with n8n (YouTube)](https://www.youtube.com/watch?v=jmuFP05YAmc)

**Note:** You will need to sign up for paid AI API keys (e.g., OpenAI, Claude, Gemini)

**Don't know how?** Research how to get an AI API key together with your AI copilot!

---

## The Progression

**Mini-Project 1:** You can build things ✓
**Mini-Project 2:** You can build useful finance tools ✓
**Mini-Project 3:** You can build INTELLIGENT finance tools
**Session 12:** "I can build the future of finance"

---

## What Makes This Different

Your previous tools did calculations. This tool should:

- Understand context
- Explain complex concepts
- Provide personalized insights
- Answer "why" not just "what"

---

## DRIVER Loops for AI Integration

### Loop 1: Basic AI Integration

**D - Discover**: What financial decision needs explanation, not just calculation?

- Investment analysis beyond numbers
- Risk assessment with context
- Strategic recommendations
- Jargon translation

**R - Reason**: How can AI make this smarter?

- Natural language input ("I have $10k to invest...")
- Contextual analysis ("Based on your age and goals...")
- Plain English output ("Here's what this means for you...")
- Dynamic recommendations

**I - Implement**: Connect AI using n8n or your chosen platform

- Use OpenAI, Claude, Gemini, or a local model (e.g., Ollama)
- Go beyond a single prompt. Include at least two advanced capabilities, for example:
  - External data via API calls (rates, prices, news) and incorporate into analysis
  - Multi-step reasoning or tool use (decompose tasks; call functions/HTTP nodes)
  - Structured outputs (JSON) with validation and rendering (tables/charts)
  - Memory/profile state across steps (risk tolerance, goals)
  - Scenario generation and comparison with rationale
  - Guardrails/sanity checks to prevent bad advice
  - Cost control (token budgeting, caching, truncation)

**V - Verify**: Is the AI actually helpful?

- Test with real scenarios
- Check for hallucinations
- Ensure finance accuracy

**E - Evolve**: What would make the AI more useful?

**R - Reflect**: What's different about building with AI as a component?

### Loop 2: Make It Trustworthy

Critical improvements:

- Add sources/explanations for AI advice
- Build in sanity checks
- Handle edge cases gracefully
- Make limitations clear

### Optional Loop 3+: Make It Powerful

Advanced features:

- Multi-step analysis
- Scenario comparison
- Learning from user feedback
- Integration with real data + AI insights

---

## Inspiration Examples

**AI + Simple Analysis:**

- Earnings Call Translator - "What did the CEO really say?"
- Stock News Sentiment Analyzer - "Should I worry about this headline?"
- Financial Statement Explainer - "What's wrong with this company?"
- Investment Thesis Generator - "Why buy/sell in plain English"

**AI + Personal Finance:**

- Financial Health Advisor - Analyzes your situation conversationally
- Goal-Based Investment Guide - "I want to buy a house in 5 years..."
- Spending Pattern Therapist - "Why do I keep doing this?"
- Negotiation Assistant - "How to ask for a raise based on..."

**AI + Learning:**

- Finance Concept Tutor - Explains topics at your level
- Case Study Analyzer - "What went wrong with SVB?"
- Strategy Simulator - "What if I had done X instead?"
- Jargon-Free Market Updates - News for normal humans

**Creative Combinations:**

- Warren Buffett Decision Bot - "What would Buffett do?"
- Risk Tolerance Interviewer - Discovers your real risk profile
- Financial Scenario Generator - "What could go wrong?"
- Deal Structure Optimizer - "How to make this work for everyone"

---

## Technical Leveling Up

**New Skills to Master:**

- API integration (OpenAI, Claude, etc.)
- Prompt engineering for finance
- Error handling for AI responses
- Token/cost management
- Response streaming
- Function/tool calling and structured outputs
- Retrieval-augmented generation (RAG) and web/data integrations

**Key Challenges:**

- Making AI financially accurate
- Handling ambiguous user input
- Managing API costs
- Preventing harmful advice
- Building user trust

**Ask AI for Help With:**

- "How to integrate OpenAI API with my web app"
- "Best practices for financial prompt engineering"
- "How to validate AI financial advice"
- "Streaming AI responses for better UX"

---

## Requirements

1. **Platform & Core AI Functionality**

   - Built with n8n or another platform of your choice (e.g., custom web app, Python app, Make/Zapier, LangChain/Flowise)
   - Uses AI to analyze/explain/advise; handles natural language input
   - Provides contextual, user-relevant insights (the “why,” not just the number)

2. **Advanced Capabilities (choose 2 or more)**

   - External data integration via APIs (e.g., rates, prices, news) with incorporation into analysis
   - Multi-step logic or tool use (function calling, HTTP requests, spreadsheet/code nodes)
   - Structured outputs with validation and clear rendering (tables/charts)
   - Memory/state (e.g., goals, risk tolerance) that influences recommendations
   - Scenario comparison with trade-offs and a recommendation
   - Guardrails/sanity checks + transparent disclaimers
   - Cost controls (prompt optimization, caching, token limits)

3. **Safety & Accuracy**

   - Clear disclaimers about AI limitations and appropriate use
   - At least one accuracy/robustness mechanism (sanity checks, bounds, unit tests, or cross-check prompts)
   - Appropriate for the financial domain and user audience

4. **Submission: Video Demo**

   - 2–3 minutes screen recording showing workflow (nodes/prompts/logic) and end-to-end demo
   - No public link required; keep API keys private
   - Narrate who it’s for and why it’s useful

5. **Iteration**
   - Show that you improved the tool from v1 to v2 (prompt refinement, new node, validation, or UX polish)

6. **Reflection in your video**

   - How does AI change the user experience?
   - What was hard about financial prompt engineering?
   - What ethical considerations did you face?
   - Would you trust your own tool with real money?

---

## Assessment Criteria

**Pass Requirements:**

- Successfully integrates AI for financial analysis ✓
- Provides value beyond simple calculation ✓
- Shows iterative improvement ✓
- Addresses accuracy/trust concerns ✓

**Excellence Indicators:**

- Genuinely insightful AI responses
- Elegant handling of edge cases
- Creative application of AI capabilities
- Other students want to use it
- You'd use it for real decisions

---

## Common Pitfalls

**Over-Trusting AI:** "The AI said buy, so buy!"
→ Build in verification and disclaimers

**Under-Using AI:** "It just formats the output nicely"
→ Make AI do actual analysis

**Prompt Problems:** "Explain finance" (too vague)
→ Craft specific, contextual prompts

**No Value Add:** "It's ChatGPT in a wrapper"
→ Add domain-specific intelligence

**Cost Explosion:** "Each query costs $5"
→ Optimize prompts and cache responses

---

## Ethical Considerations

Your tool will give financial guidance. Consider:

- Clear disclaimers (not financial advice)
- Transparency about AI involvement
- Protection against misuse
- Accessibility for different backgrounds
- Bias in financial recommendations

---

## The Mindset Evolution

**Mini-Project 1:** "I can build"
**Mini-Project 2:** "I can build useful finance tools"
**Mini-Project 3:** "I can build INTELLIGENT finance tools"
**Session 12:** "I can build the future of finance"

**The New Reality:** Financial analysis is transforming. Traditional tools and AI are converging to create new opportunities for those who can leverage both effectively.

**Your Edge:** You can build tools that USE AI to solve problems AI alone cannot. That's not just job security - that's leadership potential.

---

## Starting Points

1. **What financial concept confuses people?**
   → Build an AI explainer

2. **What decision do people struggle with?**
   → Build an AI advisor

3. **What analysis takes forever?**
   → Build an AI analyzer

4. **What pattern is hard to spot?**
   → Build an AI detector

---

## Pro Tips

- Paid API tiers work better
- Test prompts in ChatGPT/Claude first
- Build the UI, then add AI (not vice versa)
- Log everything for debugging
- Have non-finance friends test it

Remember: The best AI finance tool is one that makes someone say "Oh, NOW I get it!"
 
Make finance smarter, not just faster.

Ship something that thinks.
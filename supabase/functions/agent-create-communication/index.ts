import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-api-key',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

type RecipientObj = { contact_id?: number; email: string; name?: string; type?: string };

interface Body {
  communication_type:
    | 'Lead Communication'
    | 'Institution Communication'
    | 'Partner Communication'
    | 'Provider Communication'
    | 'Application Communication';
  entity_id: number;
  message_content: string;
  subject?: string;
  to?: RecipientObj[];
  cc?: RecipientObj[] | string[];
  bcc?: RecipientObj[] | string[];
  attachments?: Array<{ name: string; url: string; type?: string }>;
  mentioned_users?: Array<{ email: string; name: string }>;
  parent_communication_id?: number;
  from_email?: string;
}

const ALLOWED_TYPES = new Set<Body['communication_type']>([
  'Lead Communication',
  'Institution Communication',
  'Partner Communication',
  'Provider Communication',
  'Application Communication',
]);

const EMAIL_TYPES = new Set<Body['communication_type']>([
  'Lead Communication',
  'Institution Communication',
  'Partner Communication',
  'Provider Communication',
]);

const FIXED_SENDER_NAME = 'Kareem (Studygram AI Assistant)';

// Upper bound for the internal send-communication-email invocation so a slow or
// hung downstream can never keep this worker alive long enough to be recycled
// into a gateway 502.
const EMAIL_DISPATCH_TIMEOUT_MS = 30_000;

function inferDocType(name: string, mime?: string): string {
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : '';
  const m = mime || '';
  if (m.includes('pdf') || ext === 'pdf') return 'pdf';
  if (m.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return 'image';
  if (m.includes('word') || ['doc', 'docx'].includes(ext)) return 'document';
  if (m.includes('sheet') || ['xls', 'xlsx', 'csv'].includes(ext)) return 'spreadsheet';
  return 'other';
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function json(status: number, payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

// Fire the downstream email function. Runs in the background (via
// EdgeRuntime.waitUntil) so the caller is never blocked on Microsoft Graph.
async function dispatchEmail(communicationId: number, supabaseUrl: string, anonKey: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), EMAIL_DISPATCH_TIMEOUT_MS);
  try {
    const resp = await fetch(`${supabaseUrl}/functions/v1/send-communication-email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${anonKey}`,
        'apikey': anonKey,
        // Internal shared secret authorizes bypass of user-auth check on the target function.
        'x-internal-secret': Deno.env.get('INTERNAL_INVOKE_SECRET') ?? '',
      },
      body: JSON.stringify({ communication_id: communicationId }),
      signal: controller.signal,
    });
    if (!resp.ok) {
      const text = await resp.text();
      console.error(`send-communication-email ${resp.status} for communication ${communicationId}: ${text.substring(0, 500)}`);
    } else {
      console.log(`send-communication-email dispatched for communication ${communicationId}`);
    }
  } catch (e) {
    const reason = e instanceof Error ? e.message : 'fetch failed';
    console.error(`send-communication-email dispatch error for communication ${communicationId}: ${reason}`);
  } finally {
    clearTimeout(timer);
  }
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  try {
    if (req.method !== 'POST') return json(405, { error: 'Method not allowed' });

    const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY')!;
    const AGENT_API_KEY = Deno.env.get('AGENT_API_KEY');
    const AGENT_CONTACT_ID = Deno.env.get('AGENT_CONTACT_ID');

    const admin = createClient(SUPABASE_URL, SERVICE_KEY);

    // ---- Auth: X-API-Key (preferred, no expiry) OR Bearer JWT (fallback) ----
    const apiKeyHeader = req.headers.get('x-api-key') || req.headers.get('X-API-Key');
    const authHeader = req.headers.get('Authorization');

    let agentContact:
      | { id: number; full_name: string | null; photo: string | null; auth_user_id: string | null }
      | null = null;

    if (apiKeyHeader) {
      // Static API-key path. NO JWT required.
      if (!AGENT_API_KEY) return json(500, { error: 'AGENT_API_KEY not configured on server' });
      if (!constantTimeEqual(apiKeyHeader, AGENT_API_KEY)) return json(401, { error: 'Invalid API key' });
      if (!AGENT_CONTACT_ID) return json(500, { error: 'AGENT_CONTACT_ID not configured on server' });

      const { data, error } = await admin
        .from('contacts')
        .select('id, full_name, photo, auth_user_id')
        .eq('id', Number(AGENT_CONTACT_ID))
        .maybeSingle();
      if (error || !data) {
        console.error('agent contact lookup failed', error);
        return json(500, { error: 'Agent contact not found' });
      }
      agentContact = data;
    } else if (authHeader?.startsWith('Bearer ')) {
      const token = authHeader.slice('Bearer '.length);
      const authClient = createClient(SUPABASE_URL, ANON_KEY);
      const { data: claimsData, error: claimsError } = await authClient.auth.getClaims(token);
      if (claimsError || !claimsData?.claims?.sub) {
        return json(401, { error: 'Invalid or expired token' });
      }
      const authUserId = claimsData.claims.sub as string;
      const { data, error } = await admin
        .from('contacts')
        .select('id, full_name, photo, auth_user_id')
        .eq('auth_user_id', authUserId)
        .maybeSingle();
      if (error) {
        console.error('agent lookup error', error);
        return json(500, { error: 'Failed to resolve agent identity' });
      }
      if (!data) return json(403, { error: 'No contact mapped to this auth user' });
      if (AGENT_CONTACT_ID && String(data.id) !== String(AGENT_CONTACT_ID)) {
        return json(403, { error: 'This auth user is not authorised to use the agent endpoint' });
      }
      agentContact = data;
    } else {
      return json(401, { error: 'Missing X-API-Key or Authorization bearer token' });
    }

    // ---- Parse + validate body ----
    let body: Body;
    try {
      body = await req.json();
    } catch {
      return json(400, { error: 'Invalid JSON body' });
    }

    const errors: string[] = [];
    if (!body.communication_type || !ALLOWED_TYPES.has(body.communication_type)) {
      errors.push(`communication_type must be one of: ${[...ALLOWED_TYPES].join(', ')}`);
    }
    if (!body.entity_id || typeof body.entity_id !== 'number') errors.push('entity_id (number) is required');
    if (!body.message_content || typeof body.message_content !== 'string') errors.push('message_content (string) is required');
    if (errors.length) return json(400, { error: 'Validation failed', details: errors });

    // ---- Build row ----
    const metadata: Record<string, unknown> = {};
    if (body.subject) metadata.subject = body.subject;
    if (body.to) metadata.to = body.to;
    if (body.cc) metadata.cc = body.cc;
    if (body.bcc) metadata.bcc = body.bcc;
    if (body.from_email) metadata.from_email = body.from_email;

    const row: Record<string, unknown> = {
      communication_type: body.communication_type,
      message_content: body.message_content,
      sender_id: agentContact.auth_user_id,
      sender_fullname: FIXED_SENDER_NAME,
      sender_photo: agentContact.photo || '',
      sender_type: 'User',
      date_timestamp: new Date().toISOString(),
      status: 'draft',
      attachments: body.attachments || [],
      mentioned_users: body.mentioned_users || [],
      parent_communication_id: body.parent_communication_id ?? null,
      metadata,
    };

    switch (body.communication_type) {
      case 'Lead Communication':
        row.applicant_id = body.entity_id;
        break;
      case 'Institution Communication':
      case 'Partner Communication':
      case 'Provider Communication':
        row.applicant_id = null;
        row.org_id = body.entity_id;
        break;
      case 'Application Communication':
        row.applicant_id = null;
        row.application_id = body.entity_id;
        break;
    }

    const { data: inserted, error: insertErr } = await admin
      .from('communications')
      .insert(row)
      .select()
      .single();

    if (insertErr || !inserted) {
      console.error('insert error', insertErr);
      return json(500, { error: 'Failed to create communication', details: insertErr?.message });
    }

    // ---- Mirror attachments → documents (lead/org only) ----
    const attachments = body.attachments || [];
    if (attachments.length > 0 && body.communication_type !== 'Application Communication') {
      const docRows = attachments
        .filter((a) => a?.url)
        .map((a) => {
          const base: Record<string, unknown> = {
            document_name: a.name || 'Attachment',
            document_type: inferDocType(a.name || '', a.type),
            document_url: a.url,
            uploaded_by_user_id: agentContact!.auth_user_id,
            communication_id: inserted.id,
            document_description: '',
          };
          if (body.communication_type === 'Lead Communication') {
            base.applicant_id = body.entity_id;
          } else {
            base.org_id = body.entity_id;
          }
          return base;
        });

      if (docRows.length) {
        const { error: docErr } = await admin.from('documents').insert(docRows);
        if (docErr) console.error('documents mirror error', docErr);
      }
    }

    // ---- Trigger email in the background ----
    // The communication row is already durably written above, which is the only
    // work the caller needs synchronously. Dispatching the email (Microsoft Graph
    // auth + send, typically 2-4s) in the background via EdgeRuntime.waitUntil keeps
    // this request short and avoids the caller ever seeing a worker/gateway 502 that
    // was being masked as an application failure while we waited on the downstream.
    let emailQueued = false;
    if (EMAIL_TYPES.has(body.communication_type)) {
      const task = dispatchEmail(inserted.id, SUPABASE_URL, ANON_KEY);
      // deno-lint-ignore no-explicit-any
      const runtime = (globalThis as any).EdgeRuntime;
      if (runtime && typeof runtime.waitUntil === 'function') {
        runtime.waitUntil(task);
      } else {
        // Fallback for environments without EdgeRuntime: keep prior behaviour and await.
        await task;
      }
      emailQueued = true;
    }

    return json(200, {
      success: true,
      communication_id: inserted.id,
      status: inserted.status,
      // Retained for backward compatibility: true means the email was accepted for
      // delivery (queued for background dispatch), not that Graph has confirmed send.
      email_dispatched: emailQueued,
      email_queued: emailQueued,
    });
  } catch (err) {
    console.error('agent-create-communication fatal', err);
    return json(500, { error: err instanceof Error ? err.message : 'Unknown error' });
  }
});

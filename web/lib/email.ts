import { SESClient, SendEmailCommand } from '@aws-sdk/client-ses';

const sesClient = new SESClient({
  region: process.env.AWS_SES_REGION || 'ca-central-1',
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID || '',
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY || '',
  },
});

const FROM_EMAIL = process.env.AWS_SES_FROM_EMAIL || 'neartax@vitalpoint.ai';

interface EmailParams {
  to: string;
  subject: string;
  html: string;
  text?: string;
}

export async function sendEmail({ to, subject, html, text }: EmailParams): Promise<boolean> {
  try {
    const command = new SendEmailCommand({
      Source: FROM_EMAIL,
      Destination: {
        ToAddresses: [to],
      },
      Message: {
        Subject: {
          Data: subject,
          Charset: 'UTF-8',
        },
        Body: {
          Html: {
            Data: html,
            Charset: 'UTF-8',
          },
          ...(text && {
            Text: {
              Data: text,
              Charset: 'UTF-8',
            },
          }),
        },
      },
    });

    await sesClient.send(command);
    console.log(`[Email] Sent to ${to}: ${subject}`);
    return true;
  } catch (error) {
    console.error(`[Email] Failed to send to ${to}:`, error);
    return false;
  }
}

export async function sendAccountantInviteEmail(params: {
  toEmail: string;
  inviterName: string;
  inviteUrl: string;
  permissionLevel: 'read' | 'readwrite';
  personalMessage?: string;
}): Promise<boolean> {
  const { toEmail, inviterName, inviteUrl, permissionLevel, personalMessage } = params;

  const permissionText = permissionLevel === 'read' 
    ? 'view reports and download exports'
    : 'view and edit tax records';

  const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { text-align: center; padding: 20px 0; }
    .logo { font-size: 24px; font-weight: bold; color: #2563eb; }
    .content { background: #f8fafc; border-radius: 8px; padding: 30px; margin: 20px 0; }
    .button { display: inline-block; background: #2563eb; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; font-weight: 500; }
    .footer { text-align: center; color: #64748b; font-size: 14px; padding: 20px 0; }
    .message { background: #e0f2fe; border-left: 4px solid #0284c7; padding: 15px; margin: 15px 0; border-radius: 0 4px 4px 0; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">NearTax</div>
    </div>
    
    <div class="content">
      <h2>You're Invited!</h2>
      
      <p><strong>${inviterName}</strong> has invited you to access their NearTax account as their accountant.</p>
      
      <p>You'll be able to <strong>${permissionText}</strong> for their crypto tax records.</p>
      
      ${personalMessage ? `
      <div class="message">
        <p style="margin: 0; font-style: italic;">"${personalMessage}"</p>
      </div>
      ` : ''}
      
      <p style="text-align: center; margin: 30px 0;">
        <a href="${inviteUrl}" class="button">Accept Invitation</a>
      </p>
      
      <p style="font-size: 14px; color: #64748b;">
        This invitation expires in 7 days. If you didn't expect this invitation, you can safely ignore this email.
      </p>
    </div>
    
    <div class="footer">
      <p>NearTax - Crypto Tax Made Simple</p>
      <p style="font-size: 12px;">This email was sent by NearTax on behalf of ${inviterName}.</p>
    </div>
  </div>
</body>
</html>
  `;

  const text = `
You're Invited to NearTax!

${inviterName} has invited you to access their NearTax account as their accountant.

You'll be able to ${permissionText} for their crypto tax records.

${personalMessage ? `Message from ${inviterName}: "${personalMessage}"` : ''}

Accept the invitation here: ${inviteUrl}

This invitation expires in 7 days.

---
NearTax - Crypto Tax Made Simple
  `;

  return sendEmail({
    to: toEmail,
    subject: `${inviterName} invited you to access their NearTax account`,
    html,
    text,
  });
}

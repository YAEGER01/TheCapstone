# Pre-existing schema drift (index/table name alignment detected by Django).
# Left UNAPPLIED on purpose: the live database already works with these names
# and the automatic rename fails on index-name drift. Reconcile manually later.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0117_fund_report_custom_content'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='fundtransaction',
            new_name='fund_transa_directi_6f3d56_idx',
            old_name='FUND_TRANSA_directi_c179cb_idx',
        ),

        migrations.RenameIndex(
            model_name='fundtransaction',
            new_name='fund_transa_source__dbfb67_idx',
            old_name='FUND_TRANSA_source__6023fe_idx',
        ),

        migrations.RenameIndex(
            model_name='globalaudittrail',
            new_name='global_audi_table_n_2b627d_idx',
            old_name='GLOBAL_AUDI_table_n_f2953e_idx',
        ),

        migrations.RenameIndex(
            model_name='memberledger',
            new_name='member_ledg_member__159877_idx',
            old_name='MEMBER_LEDG_member__9bc074_idx',
        ),

        migrations.RenameIndex(
            model_name='memberledger',
            new_name='member_ledg_transac_f0013b_idx',
            old_name='MEMBER_LEDG_transac_4c41b6_idx',
        ),

        migrations.RenameIndex(
            model_name='memberledger',
            new_name='member_ledg_recorde_aeb626_idx',
            old_name='MEMBER_LEDG_recorde_fa4ecd_idx',
        ),

        migrations.RenameIndex(
            model_name='payrolldeduction',
            new_name='payroll_ded_batch_i_cd4980_idx',
            old_name='PAYROLL_DED_batch_i_0b9b21_idx',
        ),

        migrations.RenameIndex(
            model_name='payrolldeduction',
            new_name='payroll_ded_member__faf0a3_idx',
            old_name='PAYROLL_DED_member__4008e1_idx',
        ),

        migrations.RenameIndex(
            model_name='sensitivereadlog',
            new_name='sensitive_r_module_383e79_idx',
            old_name='SENSITIVE_R_module_b2b1eb_idx',
        ),

        migrations.RenameIndex(
            model_name='sensitivereadlog',
            new_name='sensitive_r_timesta_a57473_idx',
            old_name='SENSITIVE_R_timesta_d47548_idx',
        ),

        migrations.RenameIndex(
            model_name='supportingproof',
            new_name='supporting__content_7774ad_idx',
            old_name='SUPPORTING__content_09c351_idx',
        ),

        migrations.RenameIndex(
            model_name='supportingproof',
            new_name='supporting__uploade_6ba620_idx',
            old_name='SUPPORTING__uploade_b01f8c_idx',
        ),

        migrations.AlterModelTable(
            name='accesssession',
            table='access_session',
        ),

        migrations.AlterModelTable(
            name='aidtrackingpost',
            table='aid_tracking_post',
        ),

        migrations.AlterModelTable(
            name='album',
            table='album',
        ),

        migrations.AlterModelTable(
            name='announcement',
            table='announcement',
        ),

        migrations.AlterModelTable(
            name='announcementcategory',
            table='announcement_category',
        ),

        migrations.AlterModelTable(
            name='attendance',
            table='attendance',
        ),

        migrations.AlterModelTable(
            name='auditfindingsreport',
            table='audit_findings_report',
        ),

        migrations.AlterModelTable(
            name='backupjob',
            table='backup_job',
        ),

        migrations.AlterModelTable(
            name='category',
            table='category',
        ),

        migrations.AlterModelTable(
            name='certificate',
            table='certificate',
        ),

        migrations.AlterModelTable(
            name='certificatesettings',
            table='certificate_settings',
        ),

        migrations.AlterModelTable(
            name='claimant',
            table='claimant',
        ),

        migrations.AlterModelTable(
            name='contribution',
            table='contribution',
        ),

        migrations.AlterModelTable(
            name='deathaid',
            table='death_aid',
        ),

        migrations.AlterModelTable(
            name='department',
            table='department',
        ),

        migrations.AlterModelTable(
            name='document',
            table='document',
        ),

        migrations.AlterModelTable(
            name='documentactivity',
            table='document_activity',
        ),

        migrations.AlterModelTable(
            name='documentpin',
            table='document_pin',
        ),

        migrations.AlterModelTable(
            name='event',
            table='event',
        ),

        migrations.AlterModelTable(
            name='eventtype',
            table='event_type',
        ),

        migrations.AlterModelTable(
            name='financialdocumentarchive',
            table='financial_document_archive',
        ),

        migrations.AlterModelTable(
            name='fundtransaction',
            table='fund_transaction',
        ),

        migrations.AlterModelTable(
            name='globalaudittrail',
            table='global_audit_trail',
        ),

        migrations.AlterModelTable(
            name='heroslide',
            table='hero_slide',
        ),

        migrations.AlterModelTable(
            name='loginattemptlog',
            table='login_attempt_log',
        ),

        migrations.AlterModelTable(
            name='medicalaid',
            table='medical_aid',
        ),

        migrations.AlterModelTable(
            name='member',
            table='member',
        ),

        migrations.AlterModelTable(
            name='memberledger',
            table='member_ledger',
        ),

        migrations.AlterModelTable(
            name='memberregistrationrequest',
            table='member_registration_request',
        ),

        migrations.AlterModelTable(
            name='membershipfee',
            table='membership_fee',
        ),

        migrations.AlterModelTable(
            name='minutes',
            table='minutes',
        ),

        migrations.AlterModelTable(
            name='monthlydues',
            table='monthly_dues',
        ),

        migrations.AlterModelTable(
            name='newsarticle',
            table='news_article',
        ),

        migrations.AlterModelTable(
            name='newscategory',
            table='news_category',
        ),

        migrations.AlterModelTable(
            name='newsgallery',
            table='news_gallery',
        ),

        migrations.AlterModelTable(
            name='notification',
            table='notification',
        ),

        migrations.AlterModelTable(
            name='officerprofile',
            table='officer_profile',
        ),

        migrations.AlterModelTable(
            name='officeruser',
            table='officer_user',
        ),

        migrations.AlterModelTable(
            name='organizationfundreport',
            table='organization_fund_report',
        ),

        migrations.AlterModelTable(
            name='outgoingemail',
            table='outgoing_email',
        ),

        migrations.AlterModelTable(
            name='payrollbatch',
            table='payroll_batch',
        ),

        migrations.AlterModelTable(
            name='payrolldeduction',
            table='payroll_deduction',
        ),

        migrations.AlterModelTable(
            name='photo',
            table='photo',
        ),

        migrations.AlterModelTable(
            name='pushsubscription',
            table='push_subscription',
        ),

        migrations.AlterModelTable(
            name='sensitivereadlog',
            table='sensitive_read_log',
        ),

        migrations.AlterModelTable(
            name='supportingproof',
            table='supporting_proof',
        ),

        migrations.AlterModelTable(
            name='systemsetting',
            table='system_setting',
        ),
    ]

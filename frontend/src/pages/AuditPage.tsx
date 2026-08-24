import { useQuery } from "@tanstack/react-query";
import { Activity, Calendar, ClipboardCheck, Filter, Search, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { Badge, EmptyState, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { dateTime } from "../lib/format";

interface AuditEntry { id: number; actor_id: number | null; actor_username: string; action: string; category: string; entity_type: string; entity_id: string | null; summary: string; details: Record<string, unknown> | null; ip_address: string | null; created_at: string }
interface AuditPageData { items: AuditEntry[]; total: number; page: number; page_size: number }
interface Facets { categories: string[]; actions: string[]; users: Array<{id:number;username:string;full_name:string}> }

const tone: Record<string,string> = { security: "warning", approvals: "info", inventory: "success", orders: "info", users: "violet", kitchen: "warning", daily_needs: "warning", system: "neutral", menu: "violet", customers: "success" };

export default function AuditPage() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [actor, setActor] = useState("");
  const [day, setDay] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), page_size: "50" });
  if(search) params.set("search",search); if(category) params.set("category",category); if(actor) params.set("actor_id",actor); if(day) params.set("day",day);
  const logs = useQuery({ queryKey: ["audit",search,category,actor,day,page], queryFn: () => api<AuditPageData>(`/audit-logs?${params}`) });
  const facets = useQuery({ queryKey: ["audit-facets"], queryFn: () => api<Facets>("/audit-logs/facets") });
  const filter = (setter: (v:string)=>void, value:string) => { setter(value); setPage(1); };
  return <div className="page-stack"><header className="page-heading"><div><span className="eyebrow">شفافیت و مسئولیت‌پذیری</span><h1>گزارش فعالیت‌ها</h1><p>خط زمانی دقیق و قابل جست‌وجو از اینکه چه کسی، چه چیزی را، چه زمانی و از کجا تغییر داده است.</p></div><div className="audit-total"><Activity size={18}/><span><strong>{new Intl.NumberFormat("fa-IR").format(logs.data?.total || 0)}</strong><small>رویداد مطابق فیلتر</small></span></div></header>
    <section className="panel audit-panel"><div className="toolbar audit-toolbar"><label className="search-box"><Search size={18}/><input value={search} onChange={(e)=>filter(setSearch,e.target.value)} placeholder="جست‌وجوی عملیات، موجودیت یا کاربر…"/></label><label className="select-with-icon"><Filter size={16}/><select value={category} onChange={(e)=>filter(setCategory,e.target.value)}><option value="">همه دسته‌ها</option>{facets.data?.categories.map((item)=><option key={item} value={item}>{categoryLabel(item)}</option>)}</select></label><label className="select-with-icon"><UserRound size={16}/><select value={actor} onChange={(e)=>filter(setActor,e.target.value)}><option value="">همه کاربران</option>{facets.data?.users.map((item)=><option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><label className="date-filter"><Calendar size={16}/><input aria-label="تاریخ" type="date" value={day} onChange={(e)=>filter(setDay,e.target.value)}/></label></div>
    {logs.isLoading ? <div className="center-loader"><Spinner/></div> : logs.data?.items.length ? <div className="audit-timeline">{logs.data.items.map((entry)=><article key={entry.id}><div className={`timeline-icon timeline-${tone[entry.category] || "neutral"}`}><ShieldCheck size={18}/></div><div className="timeline-main"><div><Badge tone={tone[entry.category]||"neutral"}>{categoryLabel(entry.category)}</Badge><strong>{translateSummary(entry.summary)}</strong></div><p><b>@{entry.actor_username}</b> · {actionLabel(entry.action)} · {entityLabel(entry.entity_type)}{entry.entity_id ? ` #${entry.entity_id}`:""}</p>{entry.details && <details><summary>مشاهده جزئیات دقیق تغییر</summary><pre>{JSON.stringify(entry.details,null,2)}</pre></details>}</div><div className="timeline-meta"><strong>{dateTime(entry.created_at)}</strong><small>{entry.ip_address || "داخلی"}</small></div></article>)}</div> : <EmptyState icon={<ClipboardCheck/>} title="فعالیتی مطابق فیلتر نیست" text="برای بررسی بخش دیگری از خط زمانی، فیلترها را تغییر دهید."/>}
    {(logs.data?.total||0)>50 && <div className="pagination"><button disabled={page===1} onClick={()=>setPage(page-1)}>قبلی</button><span>صفحه {new Intl.NumberFormat("fa-IR").format(page)} از {new Intl.NumberFormat("fa-IR").format(Math.ceil((logs.data?.total||0)/50))}</span><button disabled={page>=Math.ceil((logs.data?.total||0)/50)} onClick={()=>setPage(page+1)}>بعدی</button></div>}</section>
  </div>;
}

function categoryLabel(value: string): string {
  return ({ security: "امنیت", approvals: "تأییدها", inventory: "انبار", orders: "سفارش‌ها", users: "کاربران", kitchen: "آشپزخانه", daily_needs: "نیازهای روزانه", system: "سامانه", menu: "منو", customers: "مشتریان" } as Record<string,string>)[value] || value;
}

function actionLabel(value: string): string {
  return ({ create: "ایجاد", update: "ویرایش", delete: "حذف", archive: "بایگانی", receive: "ورود کالا", adjust: "اصلاح موجودی", waste: "ضایعات", login: "ورود", login_failed: "ورود ناموفق", bootstrap: "راه‌اندازی اولیه", status_change: "تغییر وضعیت", image_update: "تغییر تصویر", price_change_requested: "درخواست تغییر قیمت", price_changed: "تغییر قیمت", price_change_approved: "تأیید قیمت", price_change_rejected: "رد قیمت", daily_need_approved: "تأیید نیاز خرید", daily_need_rejected: "رد نیاز خرید" } as Record<string,string>)[value] || value.replaceAll("_"," ");
}

function entityLabel(value: string): string {
  return ({ user: "کاربر", session: "نشست", category: "دسته‌بندی", inventory_item: "کالای انبار", stock_movement: "گردش موجودی", price_change_request: "درخواست قیمت", customer: "مشتری", menu_item: "محصول منو", order: "سفارش", recipe: "دستور پخت", daily_need: "نیاز روزانه" } as Record<string,string>)[value] || value;
}

function translateSummary(summary: string): string {
  return summary
    .replace(/^Signed in$/, "ورود موفق به سامانه")
    .replace(/^Failed login for (.+)$/, "ورود ناموفق برای $1")
    .replace(/^Created (.+) account (.+)$/, "حساب $2 با نقش $1 ایجاد شد")
    .replace(/^Updated account (.+)$/, "حساب $1 ویرایش شد")
    .replace(/^Placed order (.+) for (.+)$/, "سفارش $1 برای $2 ثبت شد")
    .replace(/^Changed (.+) from (.+) to (.+)$/, "وضعیت $1 از $2 به $3 تغییر کرد")
    .replace(/^Created inventory item (.+)$/, "کالای $1 در انبار ایجاد شد")
    .replace(/^Updated inventory item (.+)$/, "کالای $1 ویرایش شد")
    .replace(/^Created inventory category (.+)$/, "دسته‌بندی $1 ایجاد شد")
    .replace(/^Created recipe for (.+)$/, "دستور پخت $1 ایجاد شد")
    .replace(/^Updated recipe for (.+)$/, "دستور پخت $1 ویرایش شد")
    .replace(/^Registered customer (.+)$/, "مشتری $1 ثبت شد");
}

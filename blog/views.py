from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import ListView, DetailView

from blog.models import Post
from personal_finance.models import PersonalTransaction


class PostListView(LoginRequiredMixin, ListView):
    model = Post
    template_name = 'blog/post_list.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        return Post.objects.verified().select_related('author', 'linked_category')


class PostDetailView(LoginRequiredMixin, DetailView):
    model = Post
    template_name = 'blog/post_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        return Post.objects.verified()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object

        if self.request.user and self.request.user.is_authenticated and post.linked_category:
            start_month = timezone.now().replace(day=1, hour=0, minute=0, second=0)

            total_spent = PersonalTransaction.objects.filter(
                user=self.request.user,
                operation_type='expense',
                category=post.linked_category,
                date__gte=start_month
            ).aggregate(total_sum=Sum("total"))['total_sum'] or 0

            context['user_category_spent'] = total_spent
        return context
import com.intellij.lang.ASTNode;
import com.intellij.lang.ParserDefinition;
import com.intellij.lang.impl.PsiBuilderImpl;
import com.intellij.lexer.Lexer;
import com.intellij.lexer.MergingLexerAdapter;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.Application;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.ComponentManager;
import com.intellij.openapi.extensions.ExtensionPoint;
import com.intellij.openapi.extensions.Extensions;
import com.intellij.openapi.extensions.impl.ExtensionsAreaImpl;
import com.intellij.openapi.project.Project;
import com.intellij.psi.impl.source.CharTableImpl;
import com.intellij.psi.impl.source.tree.LazyParseableElement;
import com.intellij.util.CharTable;
import com.intellij.psi.tree.IElementType;
import com.intellij.psi.tree.TokenSet;
import com.jetbrains.python.PyElementTypesFacade;
import com.jetbrains.python.PyElementTypesFacadeImpl;
import com.jetbrains.python.PyTokenTypes;
import com.jetbrains.python.PythonDialectsTokenSetContributor;
import com.jetbrains.python.PythonDialectsTokenSetProvider;
import com.jetbrains.python.lexer.PythonIndentingLexer;
import com.jetbrains.python.parsing.SageParser;
import com.starnotesxj.sageide.parser.SageCaretLexer;
import com.starnotesxj.sageide.parser.SageParserDefinition;
import com.starnotesxj.sageide.sugar.SageFileElementType;
import kotlin.jvm.functions.Function0;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

/**
 * Runs the REAL parser chain end to end:
 * PythonIndentingLexer -> MergingLexerAdapter(XOR) -> SageCaretLexer
 * -> PsiBuilderImpl -> SageParser, and dumps the resulting PSI tree so
 * PsiErrorElements ("Expression expected") can be seen directly.
 */
public class TestSageParse {

  public static void main(String[] args) throws Exception {
    ComponentManager fakeManager = (ComponentManager)Proxy.newProxyInstance(
      ComponentManager.class.getClassLoader(),
      new Class<?>[]{ComponentManager.class},
      (proxy, method, a) -> defaultFor(method, proxy, a));
    ExtensionsAreaImpl area = new ExtensionsAreaImpl(fakeManager);
    Extensions.setRootArea(area);
    Disposable fakeDisposable = (Disposable)Proxy.newProxyInstance(
      Disposable.class.getClassLoader(), new Class<?>[]{Disposable.class}, (proxy, method, a) -> null);
    area.registerExtensionPoint(
      PythonDialectsTokenSetContributor.EP_NAME,
      PythonDialectsTokenSetContributor.EP_NAME.getName(),
      ExtensionPoint.Kind.INTERFACE,
      fakeDisposable);
    area.registerExtensionPoint("com.intellij.lang.ast.factory", "com.intellij.lang.ast.factory",
                                ExtensionPoint.Kind.INTERFACE, false);
    final PythonDialectsTokenSetProvider provider = new PythonDialectsTokenSetProvider();

    Application fakeApp = (Application)Proxy.newProxyInstance(
      Application.class.getClassLoader(),
      new Class<?>[]{Application.class},
      (proxy, method, a) -> {
        if (method.getName().equals("getService") && a.length == 1 &&
            a[0] == PythonDialectsTokenSetProvider.class) {
          return provider;
        }
        if (method.getName().equals("getService") && a.length == 1 &&
            a[0] == PyElementTypesFacade.class) {
          return new PyElementTypesFacadeImpl();
        }
        if (method.getName().equals("getExtensionArea")) {
          return area;
        }
        return defaultFor(method, proxy, a);
      });
    ApplicationManager.setApplication(fakeApp);

    Project fakeProject = (Project)Proxy.newProxyInstance(
      Project.class.getClassLoader(),
      new Class<?>[]{Project.class},
      (proxy, method, a) -> defaultFor(method, proxy, a));

    String[] cases = {
      "m = 1\nn = 1\nm ^^=1\nprint(m)\n",
      "e ^^= b",
      "e^254",
      "x ^^ y",
      "x ^= y",
      "F.<a> = GF(2^8, 'a')\nR.<x> = GF(2)[]\n",
      "# \u5fc5\u987b\u6307\u5b9a modulus=0x11B\uff01\nfrom six import byte2int, int2byte\n\nR.<x> = GF(2)[]\nF.<a> = GF(2^8, modulus=x^8 + x^4 + x^3 + x + 1)\n\ne = F.from_integer(0x57)\nprint('e =', e, '|', e.to_integer(), '|', e.polynomial())\nb = F.from_integer(0x83)\nprint('0x57 * 0x83 =', e * b, '|', (e * b).to_integer() == 0xC1)\nprint('a + b =', a + b, '| a - b =', a - b, '| a / b =', a / b)\nm = 1\nn = 1\nm ^^=1\nprint(m)\n\n\nprint('e \u7684\u9006\u5143 =', e^(-1), '| e^254 =', e^254, '|', e^(-1) == e^254)\nprint('x \u7684\u9636 =', a.multiplicative_order(), '(51)')\n\ng = F.multiplicative_generator()\nprint('\u672c\u539f\u5143 g =', g, '| log_g(e) =', e.log(g), '|', g^e.log(g) == e)\n\nprint('\u7279\u5f81:', F.characteristic(), '| \u5143\u7d20\u4e2a\u6570:', F.order())\nprint('modulus:', F.modulus())\nprint('\u968f\u673a\u5143\u7d20:', F.random_element())\n"
    };
    for (String text : cases) {
      System.out.println("=== " + text.replace("\n", "\\n"));
      ASTNode root = parse(fakeProject, text);
      dump(root, 0);
    }
  }

  static Object defaultFor(Method method, Object proxy, Object[] a) {
    if (method.getName().equals("toString")) return "Fake";
    if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
    if (method.getName().equals("equals")) return proxy == a[0];
    Class<?> rt = method.getReturnType();
    if (rt == boolean.class) return false;
    if (rt == int.class) return 0;
    if (rt == long.class) return 0L;
    if (rt == char.class) return '\0';
    return null;
  }

  static ASTNode parse(Project project, String text) {
    Lexer lexer = new SageCaretLexer(new Function0<Lexer>() {
      @Override
      public Lexer invoke() {
        return new MergingLexerAdapter(new PythonIndentingLexer(), TokenSet.create(PyTokenTypes.XOR));
      }
    });
    ParserDefinition definition = new SageParserDefinition();
    LazyParseableElement root = new LazyParseableElement(SageFileElementType.INSTANCE, text);
    root.putUserData(CharTable.CHAR_TABLE_KEY, new CharTableImpl());
    PsiBuilderImpl builder = new PsiBuilderImpl(project, definition, lexer, root, text);
    ASTNode tree = new SageParser().parse(SageFileElementType.INSTANCE, builder);
    return tree;
  }

  static void dump(ASTNode node, int depth) {
    StringBuilder indent = new StringBuilder();
    for (int i = 0; i < depth; i++) indent.append("  ");
    IElementType type = node.getElementType();
    String text = node.getText();
    String shortText = text == null ? "" : text.replace("\n", "\\n");
    if (shortText.length() > 60) shortText = shortText.substring(0, 60) + "...";
    System.out.println(indent.toString() + type + "  '" + shortText + "'");
    ASTNode child = node.getFirstChildNode();
    while (child != null) {
      dump(child, depth + 1);
      child = child.getTreeNext();
    }
  }
}
